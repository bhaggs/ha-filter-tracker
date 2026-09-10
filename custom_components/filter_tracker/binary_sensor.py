"""Binary sensor platform for Filter Tracker integration.

Provides a 'problem' device class binary sensor that indicates when a filter
has expired based on its installation date and lifespan.
"""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import homeassistant.util.dt as dt_util

from .base import BaseFilterEntity, FilterEntityMeta

# "key" forms the unique_id and is frozen -- see sensor.py.
BINARY_SENSOR_DEFINITIONS = {
    "expired": FilterEntityMeta(
        key="expired",
        name="Filter expired",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Filter Tracker binary sensor from config entry."""
    async_add_entities(
        [
            FilterExpiredBinarySensor(
                hass, config_entry, BINARY_SENSOR_DEFINITIONS["expired"]
            )
        ]
    )


class FilterExpiredBinarySensor(BaseFilterEntity, BinarySensorEntity):
    """Binary sensor that is 'on' when filter is expired."""

    @property
    def is_on(self) -> bool:
        """Return true if the filter is past its due date."""
        return dt_util.now().date() >= self.due_date
