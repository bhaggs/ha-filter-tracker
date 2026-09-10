import logging
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_SET_FILTER_REPLACED,
    SERVICE_SET_USAGE_TIME,
    ATTR_DEVICE_ID,
    ATTR_ENTRY_ID,
    ATTR_REPLACEMENT_DATETIME,
    ATTR_USAGE_HOURS,
    ATTR_ADJUST_HOURS,
    CONF_USAGE_SENSOR,
    DATA_CALENDAR_OWNER,
    DATA_ENTRIES,
    get_usage_update_signal,
)
from .models import FilterTrackerData
from .tracker_data import (
    InstallDatetimeUnavailable,
    async_load_usage_data,
    async_remove_install_store,
    async_remove_usage_store,
    async_save_usage_data,
)
from .utils import async_initialize_install_datetime, async_set_install_datetime

_LOGGER = logging.getLogger(__name__)

# This integration is configured via config entries (UI)
# async_setup exists only for service registration
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# vol.Exclusive expresses "at most one of this group" natively; combined with
# has_at_least_one_key it gives exactly-one, which is what the two hand-rolled
# validators here used to check.
SET_FILTER_REPLACED_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Exclusive(ATTR_ENTRY_ID, "target"): cv.string,
            vol.Exclusive(ATTR_DEVICE_ID, "target"): cv.string,
            vol.Optional(ATTR_REPLACEMENT_DATETIME): cv.datetime,
        }
    ),
    cv.has_at_least_one_key(ATTR_ENTRY_ID, ATTR_DEVICE_ID),
)

SET_USAGE_TIME_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Exclusive(ATTR_ENTRY_ID, "target"): cv.string,
            vol.Exclusive(ATTR_DEVICE_ID, "target"): cv.string,
            vol.Exclusive(ATTR_USAGE_HOURS, "amount"): vol.All(
                vol.Coerce(float), vol.Range(min=0)
            ),
            vol.Exclusive(ATTR_ADJUST_HOURS, "amount"): vol.Coerce(float),
        }
    ),
    cv.has_at_least_one_key(ATTR_ENTRY_ID, ATTR_DEVICE_ID),
    cv.has_at_least_one_key(ATTR_USAGE_HOURS, ATTR_ADJUST_HOURS),
)


def _async_resolve_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    """Resolve a service call's target to a loaded config entry.

    Shared by both services, which previously carried identical copies of this
    device-to-entry lookup.
    """
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        raise HomeAssistantError("Filter Tracker is not set up.")

    entries: dict = domain_data.get(DATA_ENTRIES, {})
    entry_id: str | None = call.data.get(ATTR_ENTRY_ID)
    device_id: str | None = call.data.get(ATTR_DEVICE_ID)

    if not entry_id and device_id:
        device = dr.async_get(hass).async_get(device_id)
        if not device:
            raise HomeAssistantError("Device not found.")
        for domain, dev_entry_id in device.identifiers:
            if domain == DOMAIN:
                entry_id = dev_entry_id
                break

    if not entry_id or entry_id not in entries:
        raise HomeAssistantError("Filter Tracker entry not found.")

    config_entry = hass.config_entries.async_get_entry(entry_id)
    if config_entry is None:
        raise HomeAssistantError("Filter Tracker entry not found.")

    return config_entry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Filter Tracker.

    Services are registered here, once, and never removed. They used to be
    registered per entry and torn down when the last one unloaded, which
    silently broke any automation referencing them by name.
    """
    _ensure_domain_data(hass)
    _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Filter Tracker entry."""
    _LOGGER.debug("Setting up filter_tracker entry: %s (%s)", entry.title, entry.entry_id)

    domain_data = _ensure_domain_data(hass)
    entries = domain_data[DATA_ENTRIES]

    entries[entry.entry_id] = True

    # Resolve the install datetime once, here, before any platform is set up.
    # This is the only code path permitted to write a default, so a read failure
    # retries setup instead of silently overwriting the user's real date.
    try:
        install_datetime = await async_initialize_install_datetime(hass, entry)
    except InstallDatetimeUnavailable as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = FilterTrackerData(install_datetime=install_datetime)

    # Standard HA pattern: a config change reloads the entry, rebuilding every
    # entity from the new configuration. This replaces a bespoke dispatcher that
    # pushed config into each live entity -- which had every entity redundantly
    # updating the same device, and could not create or remove the usage-time
    # entity when a usage sensor was added or removed.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so its entities pick up the new configuration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Filter Tracker entry.

    Deliberately does NOT touch stored data: HA runs unload on every reload, not
    just on deletion, so removing the stores here destroyed the install date and
    usage hours whenever an entry was reloaded. Deletion is handled by
    async_remove_entry below.
    """
    _LOGGER.debug("Unloading filter_tracker entry: %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Clean up in-memory data
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict = domain_data.get(DATA_ENTRIES, {})
        entries.pop(entry.entry_id, None)

        # The shared calendar was removed along with this entry's platforms.
        # Releasing ownership lets the next setup recreate it -- which for a
        # reload is this same entry, moments from now.
        if domain_data.get(DATA_CALENDAR_OWNER) == entry.entry_id:
            domain_data[DATA_CALENDAR_OWNER] = None

        if not entries:
            # Services deliberately stay registered; only per-entry state goes.
            hass.data.pop(DOMAIN, None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete an entry's persisted data.

    HA calls this only when the entry is actually being removed, which is the
    one moment it is safe to discard the user's filter history.
    """
    _LOGGER.debug("Removing stored data for filter_tracker entry: %s", entry.entry_id)

    await async_remove_install_store(hass, entry.entry_id)
    await async_remove_usage_store(hass, entry.entry_id)

    # If this entry owned the shared calendar, unload has just released it and
    # the entity is gone. Re-home it onto a surviving filter, otherwise the
    # calendar stays missing until Home Assistant restarts.
    domain_data = hass.data.get(DOMAIN)
    if domain_data is None or domain_data.get(DATA_CALENDAR_OWNER) is not None:
        return

    for other in hass.config_entries.async_loaded_entries(DOMAIN):
        if other.entry_id != entry.entry_id:
            _LOGGER.debug("Re-homing Filter Tracker calendar onto %s", other.entry_id)
            hass.config_entries.async_schedule_reload(other.entry_id)
            break


def _ensure_domain_data(hass: HomeAssistant) -> dict:
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(DATA_ENTRIES, {})
    return domain_data


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's services."""

    async def async_handle_set_filter_replaced(call: ServiceCall) -> None:
        await _async_handle_set_filter_replaced(hass, call)

    async def async_handle_set_usage_time(call: ServiceCall) -> None:
        await _async_handle_set_usage_time(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FILTER_REPLACED,
        async_handle_set_filter_replaced,
        schema=SET_FILTER_REPLACED_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_USAGE_TIME,
        async_handle_set_usage_time,
        schema=SET_USAGE_TIME_SCHEMA,
    )


async def _async_handle_set_filter_replaced(hass: HomeAssistant, call: ServiceCall) -> None:
    """Record a filter replacement at a given (or current) datetime."""
    config_entry = _async_resolve_entry(hass, call)

    replacement_dt: datetime | None = call.data.get(ATTR_REPLACEMENT_DATETIME)
    effective_dt = (
        dt_util.utcnow() if replacement_dt is None else dt_util.as_utc(replacement_dt)
    )

    await async_set_install_datetime(hass, config_entry, effective_dt)


async def _async_handle_set_usage_time(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the set_usage_time service call."""
    config_entry = _async_resolve_entry(hass, call)
    entry_id = config_entry.entry_id

    if not config_entry.data.get(CONF_USAGE_SENSOR):
        raise HomeAssistantError(
            "Filter does not have a usage sensor configured. "
            "Cannot set usage time for calendar-only filters."
        )

    usage_data = await async_load_usage_data(hass, entry_id) or {
        "accumulated_seconds": 0.0,
        "usage_sensor_last_changed": None,
        "last_sensor_state": "off",
        "last_active": False,
    }

    usage_hours = call.data.get(ATTR_USAGE_HOURS)
    adjust_hours = call.data.get(ATTR_ADJUST_HOURS)

    if usage_hours is not None:
        new_seconds = usage_hours * 3600
    else:
        new_seconds = usage_data.get("accumulated_seconds", 0.0) + (adjust_hours * 3600)

    if new_seconds < 0:
        _LOGGER.warning(
            "Usage time would be negative (%.2f hours), clamping to 0",
            new_seconds / 3600,
        )
        new_seconds = 0.0

    last_state = usage_data.get("last_sensor_state", "off")
    last_active = bool(usage_data.get("last_active"))
    now = dt_util.utcnow()

    # Reset the timestamp so live accumulation restarts from the new total
    # rather than re-adding the interval already counted into it.
    await async_save_usage_data(
        hass,
        entry_id,
        accumulated_seconds=new_seconds,
        last_changed=now,
        last_state=last_state,
        last_active=last_active,
    )

    async_dispatcher_send(
        hass,
        get_usage_update_signal(entry_id),
        {
            "accumulated_seconds": new_seconds,
            "usage_sensor_last_changed": now,
            "last_sensor_state": last_state,
            "last_active": last_active,
        },
    )

    _LOGGER.info(
        "Updated usage time for filter %s: %.2f hours", entry_id, new_seconds / 3600
    )
