from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = "install_datetime"


def _get_store(hass, entry_id: str) -> Store:
    return Store(hass, STORE_VERSION, f"{DOMAIN}_{entry_id}_install")


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
