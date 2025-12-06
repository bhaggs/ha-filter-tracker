from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
    CONF_NAME,
    CONF_USAGE_SENSOR,
    get_install_update_signal,
    get_usage_update_signal,
)
from .tracker_data import async_save_install_datetime, async_reset_usage_data
from .base import BaseFilterEntity, BaseEntityMeta

@dataclass
class ButtonMeta(BaseEntityMeta):
    """Metadata for button entities."""
    pass

BUTTON_DEFINITIONS = {
    "reset_install_date": ButtonMeta(
        key="reset_install_date",
        name="Filter replaced",
        icon="mdi:calendar-sync",
        category=EntityCategory.CONFIG,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the reset button."""
    async_add_entities(
        [
            FilterResetInstallDateButton(
                hass,
                config_entry,
            )
        ]
    )


class FilterResetInstallDateButton(BaseFilterEntity[ButtonMeta], ButtonEntity):
    """Button to reset the install date to today."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the button."""
        data = config_entry.data
        super().__init__(
            hass,
            config_entry.entry_id,
            None,  # Button doesn't need install_datetime
            data[CONF_NAME],
            0,  # lifespan not used for button
            data.get(CONF_FILTER_TYPE),
            data.get(CONF_FILTER_SIZE),
            data.get(CONF_MANUFACTURER),
            BUTTON_DEFINITIONS["reset_install_date"],
            use_install_tracking=False,  # Button sends updates, doesn't receive them
        )
        self._config_entry = config_entry

    async def async_press(self) -> None:
        """Handle button press to reset install date and usage time."""
        # Reset install datetime
        utc_value = await async_save_install_datetime(
            self.hass,
            self._config_entry.entry_id,
            dt_util.utcnow(),
        )
        async_dispatcher_send(
            self.hass,
            get_install_update_signal(self._config_entry.entry_id),
            dt_util.as_local(utc_value),
        )

        # Reset usage time if usage sensor is configured
        if self._config_entry.data.get(CONF_USAGE_SENSOR):
            await async_reset_usage_data(self.hass, self._config_entry.entry_id)
            async_dispatcher_send(
                self.hass,
                get_usage_update_signal(self._config_entry.entry_id),
                {"accumulated_seconds": 0.0, "usage_sensor_last_changed": None, "last_sensor_state": "off"},
            )
