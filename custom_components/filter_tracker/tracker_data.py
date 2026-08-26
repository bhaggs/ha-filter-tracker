from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class InstallDatetimeUnavailable(HomeAssistantError):
    """A stored install datetime exists but could not be read.

    Deliberately distinct from "nothing stored yet", which is a legitimate None
    and means a brand-new filter. Conflating the two is what allowed a single
    transient read failure to be persisted as today's date, permanently losing
    the user's real install date.
    """

STORE_VERSION = 1
STORE_KEY = "install_datetime"
USAGE_STORE_VERSION = 1
USAGE_STORE_KEY_SECONDS = "accumulated_seconds"
USAGE_STORE_KEY_LAST_CHANGED = "usage_sensor_last_changed"
USAGE_STORE_KEY_LAST_STATE = "last_sensor_state"
# Whether the tracked entity counted as running. Derived state, persisted
# because the raw state string alone is not enough for climate entities, where
# "running" comes from the hvac_action attribute rather than the state.
#
# Added without a store version bump: it is a purely additive key, and loading
# returns None when it is absent so the caller can fall back to the old
# state-string rule. A version bump without an async_migrate_func would make
# Store read the whole file as empty and lose the user's accumulated hours.
USAGE_STORE_KEY_LAST_ACTIVE = "last_active"


def _get_store(hass, entry_id: str) -> Store:
    return Store(hass, STORE_VERSION, f"{DOMAIN}_{entry_id}_install")


def _get_usage_store(hass, entry_id: str) -> Store:
    return Store(hass, USAGE_STORE_VERSION, f"{DOMAIN}_{entry_id}_usage")


async def async_load_install_datetime(hass, entry_id: str) -> datetime | None:
    """Load the stored install datetime for an entry.

    Returns None only when nothing has been stored yet. Raises
    InstallDatetimeUnavailable when a value exists but cannot be read, so the
    caller can decline to act rather than overwriting real data with a default.
    """

    store = _get_store(hass, entry_id)
    try:
        data = await store.async_load()
    except Exception as err:
        raise InstallDatetimeUnavailable(
            f"Could not read stored install datetime for {entry_id}: {err}"
        ) from err

    if not data:
        # Nothing stored yet -- a genuinely new filter.
        return None

    if STORE_KEY not in data:
        raise InstallDatetimeUnavailable(
            f"Stored install datetime for {entry_id} is missing the "
            f"{STORE_KEY!r} key"
        )

    raw = data[STORE_KEY]
    parsed = dt_util.parse_datetime(raw) if isinstance(raw, str) else None
    if not parsed:
        raise InstallDatetimeUnavailable(
            f"Stored install datetime for {entry_id} is not a valid "
            f"datetime: {raw!r}"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())

    return dt_util.as_utc(parsed)


async def async_remove_install_store(hass, entry_id: str) -> None:
    """Delete the install datetime store for an entry."""

    await _get_store(hass, entry_id).async_remove()


async def async_remove_usage_store(hass, entry_id: str) -> None:
    """Delete the usage tracking store for an entry."""

    await _get_usage_store(hass, entry_id).async_remove()


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


async def async_load_usage_data(hass, entry_id: str) -> dict[str, Any] | None:
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
            USAGE_STORE_KEY_LAST_ACTIVE: False,
        }

    # Validate and parse
    accumulated_seconds = data.get(USAGE_STORE_KEY_SECONDS, 0.0)
    last_changed_str = data.get(USAGE_STORE_KEY_LAST_CHANGED)
    last_state = data.get(USAGE_STORE_KEY_LAST_STATE, "off")

    # None means "written before this key existed"; the caller derives it from
    # last_state instead. Absence is not the same as False here.
    last_active = data.get(USAGE_STORE_KEY_LAST_ACTIVE)
    if not isinstance(last_active, bool):
        last_active = None

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
        USAGE_STORE_KEY_LAST_ACTIVE: last_active,
    }


async def async_save_usage_data(
    hass,
    entry_id: str,
    accumulated_seconds: float,
    last_changed: datetime | None,
    last_state: str,
    last_active: bool = False,
) -> None:
    """Persist the usage tracking data."""

    store = _get_usage_store(hass, entry_id)

    data = {
        USAGE_STORE_KEY_SECONDS: accumulated_seconds,
        USAGE_STORE_KEY_LAST_STATE: last_state,
        USAGE_STORE_KEY_LAST_ACTIVE: last_active,
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
        last_active=False,
    )
