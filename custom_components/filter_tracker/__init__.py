import logging
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_SET_FILTER_REPLACED,
    ATTR_DEVICE_ID,
    ATTR_ENTRY_ID,
    ATTR_REPLACEMENT_DATETIME,
    DATA_ENTRIES,
    get_install_update_signal,
)
from .tracker_data import async_save_install_datetime, _get_store

_LOGGER = logging.getLogger(__name__)

DATA_SERVICE_REGISTERED = "service_registered"

def _validate_service_data(data: dict) -> dict:
    """Validate that only one of entry_id or device_id is provided."""
    if ATTR_ENTRY_ID in data and ATTR_DEVICE_ID in data:
        raise vol.Invalid(
            f"Cannot specify both '{ATTR_ENTRY_ID}' and '{ATTR_DEVICE_ID}'. "
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

    await _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Filter Tracker entry."""
    _LOGGER.debug("Unloading filter_tracker entry: %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Clean up storage file
        store = _get_store(hass, entry.entry_id)
        await store.async_remove()

        # Clean up in-memory data
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict = domain_data.get(DATA_ENTRIES, {})
        entries.pop(entry.entry_id, None)

        if not entries:
            await _async_unregister_services(hass)
            hass.data.pop(DOMAIN, None)

    return unload_ok


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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FILTER_REPLACED,
        async_handle_set_filter_replaced,
        schema=SET_FILTER_REPLACED_SCHEMA,
    )
    domain_data[DATA_SERVICE_REGISTERED] = True


async def _async_unregister_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data or not domain_data.get(DATA_SERVICE_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_SET_FILTER_REPLACED)
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
