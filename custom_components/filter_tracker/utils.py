"""Utility functions for Filter Tracker integration."""

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from .tracker_data import async_load_install_datetime, async_save_install_datetime


async def async_get_install_datetime(
    hass: HomeAssistant,
    config_entry: ConfigEntry
) -> datetime:
    """Load install datetime from storage, handling temp keys and defaults.

    This function manages the installation datetime lifecycle:
    1. Checks for temporary storage key from config flow
    2. Migrates temp storage to permanent location
    3. Cleans up temporary storage key from config entry
    4. Falls back to current date if no stored value exists

    Args:
        hass: Home Assistant instance
        config_entry: The config entry for this filter

    Returns:
        The install datetime in local timezone
    """
    data = config_entry.data
    entry_id = config_entry.entry_id
    temp_storage_key = data.get("_temp_storage_key")
    utc_install: datetime

    if temp_storage_key:
        # New entry - try to load from temporary location created during config flow
        stored_dt = await async_load_install_datetime(hass, temp_storage_key)
        if stored_dt is not None:
            # Migrate to permanent location with actual entry_id
            utc_install = await async_save_install_datetime(hass, entry_id, stored_dt)

            # Defer cleanup of temp storage key to avoid triggering state changes during setup
            async def cleanup_temp_storage():
                """Clean up temporary storage key from config entry."""
                updated_data = {k: v for k, v in config_entry.data.items() if k != "_temp_storage_key"}
                hass.config_entries.async_update_entry(config_entry, data=updated_data)

            hass.async_create_task(cleanup_temp_storage())
        else:
            # Temp storage failed, use default
            default_local = dt_util.start_of_local_day(dt_util.now().date())
            utc_install = await async_save_install_datetime(hass, entry_id, default_local)
    else:
        # Existing entry - load from permanent location
        stored_dt = await async_load_install_datetime(hass, entry_id)
        if stored_dt is not None:
            utc_install = stored_dt
        else:
            # No stored datetime found, use default
            default_local = dt_util.start_of_local_day(dt_util.now().date())
            utc_install = await async_save_install_datetime(hass, entry_id, default_local)

    return dt_util.as_local(utc_install)
