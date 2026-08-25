"""Binary sensor platform for Filter Tracker integration.

Provides a 'problem' device class binary sensor that indicates when a filter
has expired based on its installation date and lifespan.
"""

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import (
    CONF_NAME,
    CONF_LIFESPAN_DAYS,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
)
from .base import BaseFilterEntity, BaseEntityMeta

@dataclass
class BinarySensorMeta(BaseEntityMeta):
    """Metadata for binary sensor entities."""
    pass

BINARY_SENSOR_DEFINITIONS = {
    "expired": BinarySensorMeta(
        key="expired",
        name="Filter expired",
        device_class="problem"
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Filter Tracker binary sensor from config entry."""
    install_local = config_entry.runtime_data.install_datetime
    data = config_entry.data

    expired_sensor = FilterExpiredBinarySensor(
        hass,
        config_entry.entry_id,
        install_local,
        data[CONF_NAME],
        data[CONF_LIFESPAN_DAYS],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    async_add_entities([expired_sensor])


class FilterExpiredBinarySensor(BaseFilterEntity[BinarySensorMeta], BinarySensorEntity):
    """Binary sensor that is 'on' when filter is expired."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        install_datetime: datetime,
        name: str,
        lifespan_days: int,
        filter_type: str | None,
        filter_size: str | None,
        manufacturer: str | None,
    ) -> None:
        super().__init__(
            hass,
            entry_id,
            install_datetime,
            name,
            lifespan_days,
            filter_type,
            filter_size,
            manufacturer,
            BINARY_SENSOR_DEFINITIONS["expired"],
        )

    @property
    def is_on(self) -> bool:
        """Return true if the filter is past its due date."""
        today = dt_util.now().date()
        return today >= self.due_date
