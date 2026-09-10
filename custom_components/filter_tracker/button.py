"""Button platform for Filter Tracker integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_USAGE_SENSOR, get_usage_update_signal
from .tracker_data import async_reset_usage_data
from .utils import async_set_install_datetime
from .base import BaseFilterEntity, FilterEntityMeta

# "key" forms the unique_id and is frozen -- see sensor.py.
BUTTON_DEFINITIONS = {
    "reset_install_date": FilterEntityMeta(
        key="reset_install_date",
        name="Filter replaced",
        icon="mdi:calendar-sync",
        category=EntityCategory.CONFIG,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the reset button."""
    async_add_entities(
        [
            FilterResetInstallDateButton(
                hass,
                config_entry,
                BUTTON_DEFINITIONS["reset_install_date"],
                # The button produces install updates rather than consuming
                # them, so it does not subscribe to its own signal.
                use_install_tracking=False,
            )
        ]
    )


class FilterResetInstallDateButton(BaseFilterEntity, ButtonEntity):
    """Button to reset the install date to today."""

    def __init__(self, hass, config_entry, meta, **kwargs) -> None:
        """Keep the config entry: pressing writes through it."""
        super().__init__(hass, config_entry, meta, **kwargs)
        self._config_entry = config_entry

    async def async_press(self) -> None:
        """Handle button press to reset install date and usage time."""
        await async_set_install_datetime(
            self.hass,
            self._config_entry,
            dt_util.utcnow(),
        )

        # Reset usage time if usage sensor is configured
        if self._config_entry.data.get(CONF_USAGE_SENSOR):
            await async_reset_usage_data(self.hass, self._config_entry.entry_id)
            async_dispatcher_send(
                self.hass,
                get_usage_update_signal(self._config_entry.entry_id),
                {
                    "accumulated_seconds": 0.0,
                    "usage_sensor_last_changed": None,
                    "last_sensor_state": "off",
                    "last_active": False,
                },
            )
