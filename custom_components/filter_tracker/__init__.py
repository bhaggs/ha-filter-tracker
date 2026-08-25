import logging
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
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
    DATA_ENTRIES,
    get_install_update_signal,
    get_usage_update_signal,
)
from .models import FilterTrackerData
from .tracker_data import (
    InstallDatetimeUnavailable,
    async_load_usage_data,
    async_remove_install_store,
    async_remove_usage_store,
    async_save_install_datetime,
    async_save_usage_data,
)
from .utils import async_initialize_install_datetime

_LOGGER = logging.getLogger(__name__)

DATA_SERVICE_REGISTERED = "service_registered"

# This integration is configured via config entries (UI)
# async_setup exists only for service registration
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

def _validate_service_data(data: dict) -> dict:
    """Validate that only one of entry_id or device_id is provided."""
    if ATTR_ENTRY_ID in data and ATTR_DEVICE_ID in data:
        raise vol.Invalid(
            f"Cannot specify both '{ATTR_ENTRY_ID}' and '{ATTR_DEVICE_ID}'. "
            "Please provide only one."
        )
    return data


def _validate_usage_time_data(data: dict) -> dict:
    """Validate usage time service data."""
    # Check entry_id/device_id
    if ATTR_ENTRY_ID in data and ATTR_DEVICE_ID in data:
        raise vol.Invalid(
            f"Cannot specify both '{ATTR_ENTRY_ID}' and '{ATTR_DEVICE_ID}'. "
            "Please provide only one."
        )

    # Check usage_hours/adjust_hours
    if ATTR_USAGE_HOURS in data and ATTR_ADJUST_HOURS in data:
        raise vol.Invalid(
            f"Cannot specify both '{ATTR_USAGE_HOURS}' and '{ATTR_ADJUST_HOURS}'. "
            "Please provide only one."
        )

    return data


SET_FILTER_REPLACED_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Optional(ATTR_DEVICE_ID): cv.string,
            vol.Optional(ATTR_REPLACEMENT_DATETIME): cv.datetime,
        }
    ),
    cv.has_at_least_one_key(ATTR_ENTRY_ID, ATTR_DEVICE_ID),
    _validate_service_data,
)

SET_USAGE_TIME_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Optional(ATTR_DEVICE_ID): cv.string,
            vol.Optional(ATTR_USAGE_HOURS): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(ATTR_ADJUST_HOURS): vol.Coerce(float),
        }
    ),
    cv.has_at_least_one_key(ATTR_ENTRY_ID, ATTR_DEVICE_ID),
    cv.has_at_least_one_key(ATTR_USAGE_HOURS, ATTR_ADJUST_HOURS),
    _validate_usage_time_data,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Filter Tracker via YAML (keeps services available)."""
    _ensure_domain_data(hass)
    await _async_register_services(hass)
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

    await _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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

        if not entries:
            await _async_unregister_services(hass)
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


def _ensure_domain_data(hass: HomeAssistant) -> dict:
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(DATA_ENTRIES, {})
    return domain_data


async def _async_register_services(hass: HomeAssistant) -> None:
    domain_data = _ensure_domain_data(hass)
    if domain_data.get(DATA_SERVICE_REGISTERED):
        return

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

    domain_data[DATA_SERVICE_REGISTERED] = True


async def _async_unregister_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data or not domain_data.get(DATA_SERVICE_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_SET_FILTER_REPLACED)
    hass.services.async_remove(DOMAIN, SERVICE_SET_USAGE_TIME)
    domain_data[DATA_SERVICE_REGISTERED] = False


async def _async_handle_set_filter_replaced(hass: HomeAssistant, call: ServiceCall) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        raise HomeAssistantError("Filter Tracker is not set up.")

    entries: dict = domain_data.get(DATA_ENTRIES, {})

    entry_id: str | None = call.data.get(ATTR_ENTRY_ID)
    device_id: str | None = call.data.get(ATTR_DEVICE_ID)

    if not entry_id and device_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            raise HomeAssistantError("Device not found.")
        for domain, dev_entry_id in device.identifiers:
            if domain == DOMAIN:
                entry_id = dev_entry_id
                break

    if not entry_id or entry_id not in entries:
        raise HomeAssistantError("Filter Tracker entry not found.")

    replacement_dt: datetime | None = call.data.get(ATTR_REPLACEMENT_DATETIME)
    if replacement_dt is None:
        effective_dt = dt_util.utcnow()
    else:
        effective_dt = dt_util.as_utc(replacement_dt)

    utc_value = await async_save_install_datetime(hass, entry_id, effective_dt)
    async_dispatcher_send(
        hass,
        get_install_update_signal(entry_id),
        dt_util.as_local(utc_value),
    )


async def _async_handle_set_usage_time(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the set_usage_time service call."""
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        raise HomeAssistantError("Filter Tracker is not set up.")

    entries: dict = domain_data.get(DATA_ENTRIES, {})

    entry_id: str | None = call.data.get(ATTR_ENTRY_ID)
    device_id: str | None = call.data.get(ATTR_DEVICE_ID)

    # Resolve entry_id from device_id if needed
    if not entry_id and device_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            raise HomeAssistantError("Device not found.")
        for domain, dev_entry_id in device.identifiers:
            if domain == DOMAIN:
                entry_id = dev_entry_id
                break

    if not entry_id or entry_id not in entries:
        raise HomeAssistantError("Filter Tracker entry not found.")

    # Check if filter has usage sensor configured
    config_entry = hass.config_entries.async_get_entry(entry_id)
    if not config_entry or not config_entry.data.get(CONF_USAGE_SENSOR):
        raise HomeAssistantError(
            "Filter does not have a usage sensor configured. "
            "Cannot set usage time for calendar-only filters."
        )

    # Load current usage data
    usage_data = await async_load_usage_data(hass, entry_id)
    if not usage_data:
        usage_data = {
            "accumulated_seconds": 0.0,
            "usage_sensor_last_changed": None,
            "last_sensor_state": "off",
        }

    current_seconds = usage_data.get("accumulated_seconds", 0.0)

    # Calculate new usage time
    usage_hours = call.data.get(ATTR_USAGE_HOURS)
    adjust_hours = call.data.get(ATTR_ADJUST_HOURS)

    if usage_hours is not None:
        # Set absolute value
        new_seconds = usage_hours * 3600
    elif adjust_hours is not None:
        # Add/subtract from current value
        new_seconds = current_seconds + (adjust_hours * 3600)
    else:
        raise HomeAssistantError("Must provide either usage_hours or adjust_hours.")

    # Clamp to minimum of 0
    if new_seconds < 0:
        _LOGGER.warning(
            "Usage time would be negative (%.2f hours), clamping to 0",
            new_seconds / 3600,
        )
        new_seconds = 0.0

    # Save updated usage data
    # Reset timestamp to now to restart dynamic accumulation timer
    await async_save_usage_data(
        hass,
        entry_id,
        accumulated_seconds=new_seconds,
        last_changed=dt_util.utcnow(),
        last_state=usage_data.get("last_sensor_state", "off"),
    )

    # Dispatch signal to update entities
    # Send current timestamp to reset dynamic accumulation timer
    async_dispatcher_send(
        hass,
        get_usage_update_signal(entry_id),
        {
            "accumulated_seconds": new_seconds,
            "usage_sensor_last_changed": dt_util.utcnow(),
            "last_sensor_state": usage_data.get("last_sensor_state", "off"),
        },
    )

    _LOGGER.info(
        "Updated usage time for filter %s: %.2f hours",
        entry_id,
        new_seconds / 3600,
    )
