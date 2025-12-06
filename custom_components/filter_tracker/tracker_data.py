from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = "install_datetime"
USAGE_STORE_VERSION = 1
USAGE_STORE_KEY_SECONDS = "accumulated_seconds"
USAGE_STORE_KEY_LAST_CHANGED = "usage_sensor_last_changed"
USAGE_STORE_KEY_LAST_STATE = "last_sensor_state"


def _get_store(hass, entry_id: str) -> Store:
    return Store(hass, STORE_VERSION, f"{DOMAIN}_{entry_id}_install")


def _get_usage_store(hass, entry_id: str) -> Store:
    return Store(hass, USAGE_STORE_VERSION, f"{DOMAIN}_{entry_id}_usage")


async def async_load_install_datetime(hass, entry_id: str) -> datetime | None:
    """Load the stored install datetime for an entry."""

    store = _get_store(hass, entry_id)
    try:
        data = await store.async_load()
    except Exception as err:
        _LOGGER.error("Failed to load install datetime for %s: %s", entry_id, err)
        return None

    if not data or STORE_KEY not in data:
        return None

    parsed = dt_util.parse_datetime(data[STORE_KEY])
    if not parsed:
        _LOGGER.debug("Invalid stored install datetime for %s", entry_id)
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())

    return dt_util.as_utc(parsed)


async def async_save_install_datetime(
    hass, entry_id: str, new_value: datetime
) -> datetime:
    """Persist the install datetime and return the UTC value."""

    if new_value.tzinfo is None:
        new_value = new_value.replace(tzinfo=dt_util.get_default_time_zone())

    utc_value = dt_util.as_utc(new_value)

    store = _get_store(hass, entry_id)
    try:
        await store.async_save({STORE_KEY: utc_value.isoformat()})
    except Exception as err:
        _LOGGER.error("Failed to save install datetime for %s: %s", entry_id, err)
        raise

    _LOGGER.debug("Stored install datetime for %s: %s", entry_id, utc_value)

    return utc_value


async def async_load_usage_data(hass, entry_id: str) -> dict[str, any] | None:
    """Load the stored usage tracking data for an entry."""

    store = _get_usage_store(hass, entry_id)
    try:
        data = await store.async_load()
    except Exception as err:
        _LOGGER.error("Failed to load usage data for %s: %s", entry_id, err)
        return None

    if not data:
        # Return default values
        return {
            USAGE_STORE_KEY_SECONDS: 0.0,
            USAGE_STORE_KEY_LAST_CHANGED: None,
            USAGE_STORE_KEY_LAST_STATE: "off",
        }

    # Validate and parse
    accumulated_seconds = data.get(USAGE_STORE_KEY_SECONDS, 0.0)
    last_changed_str = data.get(USAGE_STORE_KEY_LAST_CHANGED)
    last_state = data.get(USAGE_STORE_KEY_LAST_STATE, "off")

    last_changed = None
    if last_changed_str:
        parsed = dt_util.parse_datetime(last_changed_str)
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
            last_changed = dt_util.as_utc(parsed)

    return {
        USAGE_STORE_KEY_SECONDS: float(accumulated_seconds),
        USAGE_STORE_KEY_LAST_CHANGED: last_changed,
        USAGE_STORE_KEY_LAST_STATE: last_state,
    }


async def async_save_usage_data(
    hass,
    entry_id: str,
    accumulated_seconds: float,
    last_changed: datetime | None,
    last_state: str,
) -> None:
    """Persist the usage tracking data."""

    store = _get_usage_store(hass, entry_id)

    data = {
        USAGE_STORE_KEY_SECONDS: accumulated_seconds,
        USAGE_STORE_KEY_LAST_STATE: last_state,
    }

    if last_changed:
        if last_changed.tzinfo is None:
            last_changed = last_changed.replace(tzinfo=dt_util.get_default_time_zone())
        utc_value = dt_util.as_utc(last_changed)
        data[USAGE_STORE_KEY_LAST_CHANGED] = utc_value.isoformat()
    else:
        data[USAGE_STORE_KEY_LAST_CHANGED] = None

    try:
        await store.async_save(data)
    except Exception as err:
        _LOGGER.error("Failed to save usage data for %s: %s", entry_id, err)
        raise

    _LOGGER.debug(
        "Stored usage data for %s: %s seconds, state=%s",
        entry_id,
        accumulated_seconds,
        last_state,
    )


async def async_reset_usage_data(hass, entry_id: str) -> None:
    """Reset usage tracking data to zero."""

    await async_save_usage_data(
        hass,
        entry_id,
        accumulated_seconds=0.0,
        last_changed=None,
        last_state="off",
    )
