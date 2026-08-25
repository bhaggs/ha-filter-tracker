"""Utility functions for Filter Tracker integration."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
import homeassistant.util.dt as dt_util

from .const import CONF_TEMP_STORAGE_KEY, get_install_update_signal
from .tracker_data import (
    InstallDatetimeUnavailable,
    async_load_install_datetime,
    async_remove_install_store,
    async_save_install_datetime,
)

_LOGGER = logging.getLogger(__name__)


async def async_set_install_datetime(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    value: datetime,
) -> datetime:
    """Record a new install datetime and propagate it everywhere.

    The single writer for all three user-facing paths: the "Filter replaced"
    button, the set_filter_replaced service, and the options flow's date picker.

    Storage is not the only consumer any more -- entities update from the
    dispatcher signal and the calendar reads shared in-memory state -- so all
    three have to move together. Leaving this to each caller is what let the
    calendar drift out of step with the sensors.

    Returns the stored value in local time.
    """
    entry_id = config_entry.entry_id

    utc_value = await async_save_install_datetime(hass, entry_id, value)
    local_value = dt_util.as_local(utc_value)

    runtime_data = getattr(config_entry, "runtime_data", None)
    if runtime_data is not None:
        runtime_data.install_datetime = local_value

    async_dispatcher_send(hass, get_install_update_signal(entry_id), local_value)

    return local_value


async def async_get_install_datetime(
    hass: HomeAssistant,
    entry_id: str,
) -> datetime | None:
    """Read the install datetime for an entry, in local time.

    A pure read: it never writes, and never invents a default. Callers that
    display a value use this. Raises InstallDatetimeUnavailable if a stored
    value exists but cannot be read.
    """
    utc_install = await async_load_install_datetime(hass, entry_id)
    return dt_util.as_local(utc_install) if utc_install else None


async def async_initialize_install_datetime(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> datetime:
    """Resolve an entry's install datetime at setup, writing only if needed.

    Called exactly once per entry, from async_setup_entry, before the platforms
    are forwarded. It is the only place allowed to write a default.

    Handles the legacy config-flow handoff: the flow could not know the entry_id
    yet, so it parked the chosen date in a temp store keyed by flow_id. That key
    was cleaned up by a fire-and-forget task raced by three platforms, so it
    frequently survived -- and every later setup re-migrated the creation-time
    date over whatever the user had since set with the "Filter replaced" button.

    Returns the install datetime in local time.
    """
    entry_id = config_entry.entry_id
    temp_storage_key = config_entry.data.get(CONF_TEMP_STORAGE_KEY)

    utc_install = await async_load_install_datetime(hass, entry_id)

    if temp_storage_key:
        utc_install = await _async_migrate_temp_storage(
            hass, config_entry, temp_storage_key, utc_install
        )

    if utc_install is None:
        # Genuinely nothing stored: a new filter. This is the only write of a
        # default, and it is reachable only at setup.
        default_local = dt_util.start_of_local_day(dt_util.now().date())
        utc_install = await async_save_install_datetime(hass, entry_id, default_local)
        _LOGGER.debug("No stored install datetime for %s, defaulting to today", entry_id)

    return dt_util.as_local(utc_install)


async def _async_migrate_temp_storage(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    temp_storage_key: str,
    utc_install: datetime | None,
) -> datetime | None:
    """Migrate a legacy temp install store, then remove every trace of it.

    An existing permanent value always wins: it is either the migrated value
    from a previous setup or a newer date the user set deliberately, and the
    temp store only ever holds the original creation-time date.
    """
    entry_id = config_entry.entry_id

    if utc_install is None:
        try:
            temp_value = await async_load_install_datetime(hass, temp_storage_key)
        except InstallDatetimeUnavailable as err:
            _LOGGER.warning(
                "Could not read temporary install datetime for %s: %s", entry_id, err
            )
            temp_value = None

        if temp_value is not None:
            await async_save_install_datetime(hass, entry_id, temp_value)

            # Confirm the permanent store reads back before dropping the only
            # other copy of this date.
            utc_install = await async_load_install_datetime(hass, entry_id)
            if utc_install is None:
                _LOGGER.error(
                    "Refusing to remove temporary install store for %s: the "
                    "permanent store did not read back after writing",
                    entry_id,
                )
                return temp_value

            _LOGGER.info(
                "Migrated install datetime for %s from temporary storage", entry_id
            )
    else:
        _LOGGER.debug(
            "Ignoring stale temporary install store for %s; keeping stored value",
            entry_id,
        )

    await async_remove_install_store(hass, temp_storage_key)

    hass.config_entries.async_update_entry(
        config_entry,
        data={
            key: value
            for key, value in config_entry.data.items()
            if key != CONF_TEMP_STORAGE_KEY
        },
    )

    return utc_install
