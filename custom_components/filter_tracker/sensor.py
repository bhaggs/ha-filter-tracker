"""Sensor platform for Filter Tracker integration.

Provides sensors for tracking filter lifecycle including installation date,
due date, days remaining, and percentage of life remaining.
"""

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import (
    CONF_NAME,
    CONF_LIFESPAN_DAYS,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
    CONF_USAGE_SENSOR,
)
from .utils import async_get_install_datetime
from .base import BaseFilterEntity, BaseEntityMeta

@dataclass
class SensorMeta(BaseEntityMeta):
    """Metadata for sensor entities."""
    pass

SENSOR_DEFINITIONS = {
    "install_date": SensorMeta(
        key="install_date",
        name="Filter last replaced",
        icon="mdi:calendar-clock",
        device_class="timestamp"
    ),
    "due_date": SensorMeta(
        key="due_date",
        name="Filter replacement due date",
        icon="mdi:calendar",
        device_class="timestamp"
    ),
    "days_remaining": SensorMeta(
        key="days_remaining",
        name="Filter life days remaining",
        icon="mdi:calendar",
        unit="days"
    ),
    "life_remaining_percent": SensorMeta(
        key="life_remaining_percent",
        name="Filter life remaining",
        icon="mdi:percent-box",
        unit="%"
    ),
    "filter_type": SensorMeta(
        key="filter_type",
        name="Filter type",
        icon="mdi:air-filter",
        category=EntityCategory.DIAGNOSTIC,
    ),
    "usage_time": SensorMeta(
        key="usage_time",
        name="Usage time",
        icon="mdi:clock-outline",
        device_class="duration",
        unit="h",
        category=None,
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Filter Tracker sensor from config entry."""
    install_local = await async_get_install_datetime(hass, config_entry)
    data = config_entry.data
    entry_id = config_entry.entry_id

    install_date_sensor = FilterInstallDateSensor(
        hass,
        entry_id,
        install_local,
        data[CONF_NAME],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    due_date_sensor = FilterDueDateSensor(
        hass,
        entry_id,
        install_local,
        data[CONF_NAME],
        data[CONF_LIFESPAN_DAYS],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    days_remaining_sensor = FilterDaysRemainingSensor(
        hass,
        entry_id,
        install_local,
        data[CONF_NAME],
        data[CONF_LIFESPAN_DAYS],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    percent_remaining_sensor = FilterLifeRemainingPercentageSensor(
        hass,
        entry_id,
        install_local,
        data[CONF_NAME],
        data[CONF_LIFESPAN_DAYS],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    filter_type_sensor = FilterTypeSensor(
        hass,
        entry_id,
        install_local,
        data[CONF_NAME],
        data[CONF_LIFESPAN_DAYS],
        data.get(CONF_FILTER_TYPE),
        data.get(CONF_FILTER_SIZE),
        data.get(CONF_MANUFACTURER),
    )

    sensors = [
        install_date_sensor,
        due_date_sensor,
        days_remaining_sensor,
        percent_remaining_sensor,
        filter_type_sensor,
    ]

    # Add usage time sensor if usage sensor is configured
    if data.get(CONF_USAGE_SENSOR):
        usage_time_sensor = FilterUsageTimeSensor(
            hass,
            entry_id,
            install_local,
            data[CONF_NAME],
            data[CONF_LIFESPAN_DAYS],
            data.get(CONF_FILTER_TYPE),
            data.get(CONF_FILTER_SIZE),
            data.get(CONF_MANUFACTURER),
            data.get(CONF_USAGE_SENSOR),
        )
        sensors.append(usage_time_sensor)

    async_add_entities(sensors)


class FilterInstallDateSensor(BaseFilterEntity[SensorMeta], SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        install_datetime: datetime,
        name: str,
        filter_type: str | None,
        filter_size: str | None,
        manufacturer: str | None,
    ) -> None:
        super().__init__(
            hass,
            entry_id,
            install_datetime,
            name,
            0,
            filter_type,
            filter_size,
            manufacturer,
            SENSOR_DEFINITIONS["install_date"],
        )

    @property
    def native_value(self):
        return self.install_datetime


class FilterDueDateSensor(BaseFilterEntity[SensorMeta], SensorEntity):
    """Sensor that shows when the filter replacement is due."""

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
            SENSOR_DEFINITIONS["due_date"],
        )

    @property
    def native_value(self):
        """Return the due date as a datetime (start of day in local timezone)."""
        return dt_util.start_of_local_day(self.due_date)
    
    @property
    def icon(self):
        today = dt_util.now().date()
        if today < self.due_date:
            return "mdi:calendar"
        else:
            return "mdi:calendar-alert"


class FilterDaysRemainingSensor(BaseFilterEntity[SensorMeta], SensorEntity):
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
            SENSOR_DEFINITIONS["days_remaining"],
        )

    @property
    def native_value(self):
        today = dt_util.now().date()
        return max(0, (self.due_date - today).days)

    @property
    def icon(self):
        if self.native_value > 0:
            return "mdi:calendar"
        else:
            return "mdi:calendar-alert"


class FilterLifeRemainingPercentageSensor(BaseFilterEntity[SensorMeta], SensorEntity):
    """Sensor that shows the remaining filter life as a percentage."""

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
            SENSOR_DEFINITIONS["life_remaining_percent"],
        )

    @property
    def native_value(self):
        """Return the percentage of filter life remaining."""
        today = dt_util.now().date()
        elapsed_days = (today - self._install_datetime.date()).days
        remaining = max(0, self._lifespan_days - elapsed_days)

        if self._lifespan_days <= 0:
            return 0

        percent = (remaining / self._lifespan_days) * 100

        return min(100, round(percent))

    @property
    def icon(self):
        if self.native_value > 0:
            return "mdi:calendar"
        else:
            return "mdi:calendar-alert"


class FilterTypeSensor(BaseFilterEntity[SensorMeta], SensorEntity):
    """Diagnostic sensor displaying filter type with static metadata."""

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
            SENSOR_DEFINITIONS["filter_type"],
        )

    @property
    def native_value(self):
        """Return the filter type as the state."""
        return self._filter_type

    @property
    def extra_state_attributes(self):
        """Return static filter metadata as attributes."""
        attributes = {
            "rated_lifespan_days": self._lifespan_days,
            "install_date": self.install_datetime.isoformat() if self.install_datetime else None,
            "replacement_due_date": dt_util.start_of_local_day(self.due_date).isoformat(),
            "filter_size": self._filter_size,
            "manufacturer": self._manufacturer,
        }

        # Add usage tracking info if configured
        if self._usage_sensor_entity_id:
            attributes["usage_sensor"] = self._usage_sensor_entity_id
            attributes["usage_sensor_available"] = self._usage_sensor_available
            if not self._usage_sensor_available:
                attributes["usage_tracking_status"] = "paused - sensor unavailable"

        return attributes


class FilterUsageTimeSensor(BaseFilterEntity[SensorMeta], SensorEntity):
    """Sensor that tracks accumulated usage time based on a binary sensor."""

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
        usage_sensor_entity_id: str,
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
            SENSOR_DEFINITIONS["usage_time"],
            usage_sensor_entity_id=usage_sensor_entity_id,
        )

    @property
    def native_value(self):
        """Return accumulated usage time in hours."""
        return round(self.accumulated_usage_hours, 2)

    @property
    def extra_state_attributes(self):
        """Return usage tracking metadata as attributes."""
        return {
            "usage_sensor": self.usage_sensor_entity_id,
            "usage_sensor_available": self.usage_sensor_available,
            "usage_sensor_state": self._last_usage_sensor_state,
            "usage_sensor_last_changed": self._last_usage_changed.isoformat() if self._last_usage_changed else None,
            "accumulated_seconds": round(self.accumulated_usage_seconds, 2),
        }