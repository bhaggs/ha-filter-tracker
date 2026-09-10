"""Sensor platform for Filter Tracker integration.

Provides sensors for tracking filter lifecycle including installation date,
due date, days remaining, and percentage of life remaining.
"""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import CONF_USAGE_SENSOR
from .base import BaseFilterEntity, FilterEntityMeta

# The "key" of each definition forms the entity's unique_id and is frozen:
# renaming one orphans the user's existing entity, silently dropping its
# recorder history and breaking every dashboard card and automation using it.
SENSOR_DEFINITIONS = {
    "install_date": FilterEntityMeta(
        key="install_date",
        name="Filter last replaced",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    "due_date": FilterEntityMeta(
        key="due_date",
        name="Filter replacement due date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    "days_remaining": FilterEntityMeta(
        key="days_remaining",
        name="Filter life days remaining",
        icon="mdi:calendar",
        unit="days",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "life_remaining_percent": FilterEntityMeta(
        key="life_remaining_percent",
        name="Filter life remaining",
        icon="mdi:percent-box",
        unit="%",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "filter_type": FilterEntityMeta(
        key="filter_type",
        name="Filter type",
        icon="mdi:air-filter",
        category=EntityCategory.DIAGNOSTIC,
    ),
    "usage_time": FilterEntityMeta(
        key="usage_time",
        name="Usage time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        unit="h",
        category=None,
        # Resets to zero when the filter is replaced; TOTAL_INCREASING is the
        # state class that understands a counter restarting.
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Filter Tracker sensor from config entry."""
    sensors = [
        cls(hass, config_entry, SENSOR_DEFINITIONS[key])
        for key, cls in (
            ("install_date", FilterInstallDateSensor),
            ("due_date", FilterDueDateSensor),
            ("days_remaining", FilterDaysRemainingSensor),
            ("life_remaining_percent", FilterLifeRemainingPercentageSensor),
            ("filter_type", FilterTypeSensor),
        )
    ]

    # Only tracked filters get a usage sensor; adding or removing one reloads
    # the entry, so this list is rebuilt with the new configuration.
    usage_sensor = config_entry.data.get(CONF_USAGE_SENSOR)
    if usage_sensor:
        sensors.append(
            FilterUsageTimeSensor(
                hass,
                config_entry,
                SENSOR_DEFINITIONS["usage_time"],
                usage_sensor_entity_id=usage_sensor,
            )
        )

    async_add_entities(sensors)


class FilterInstallDateSensor(BaseFilterEntity, SensorEntity):
    """When the filter was last replaced."""

    @property
    def native_value(self):
        return self.install_datetime


class FilterDueDateSensor(BaseFilterEntity, SensorEntity):
    """Sensor that shows when the filter replacement is due."""

    @property
    def native_value(self):
        """Return the due date as a datetime (start of day in local timezone)."""
        return dt_util.start_of_local_day(self.due_date)

    @property
    def icon(self):
        today = dt_util.now().date()
        return "mdi:calendar" if today < self.due_date else "mdi:calendar-alert"


class FilterDaysRemainingSensor(BaseFilterEntity, SensorEntity):
    """Whole days left before the filter is due."""

    @property
    def native_value(self):
        today = dt_util.now().date()
        return max(0, (self.due_date - today).days)

    @property
    def icon(self):
        return "mdi:calendar" if self.native_value > 0 else "mdi:calendar-alert"


class FilterLifeRemainingPercentageSensor(BaseFilterEntity, SensorEntity):
    """Sensor that shows the remaining filter life as a percentage."""

    @property
    def native_value(self):
        """Return the percentage of filter life remaining."""
        if self._lifespan_days <= 0:
            return 0

        today = dt_util.now().date()
        elapsed_days = (today - self._install_datetime.date()).days
        remaining = max(0, self._lifespan_days - elapsed_days)

        return min(100, round((remaining / self._lifespan_days) * 100))

    @property
    def icon(self):
        return "mdi:calendar" if self.native_value > 0 else "mdi:calendar-alert"


class FilterTypeSensor(BaseFilterEntity, SensorEntity):
    """Diagnostic sensor displaying filter type with static metadata."""

    @property
    def native_value(self):
        """Return the filter type as the state."""
        return self._filter_type

    @property
    def extra_state_attributes(self):
        """Return static filter metadata as attributes.

        Deliberately excludes the install and due dates: both have dedicated
        sensors, and duplicating them here wrote two more copies into the
        recorder on every state write.
        """
        attributes = {
            "rated_lifespan_days": self._lifespan_days,
            "filter_size": self._filter_size,
            "manufacturer": self._manufacturer,
        }

        if self._usage_sensor_entity_id:
            attributes["usage_sensor"] = self._usage_sensor_entity_id
            attributes["usage_sensor_available"] = self._usage_sensor_available
            if not self._usage_sensor_available:
                attributes["usage_tracking_status"] = "paused - sensor unavailable"

        return attributes


class FilterUsageTimeSensor(BaseFilterEntity, SensorEntity):
    """Sensor that tracks accumulated usage time based on a tracked entity."""

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
            # Whether that state currently counts as running. For a climate
            # entity this is hvac_action, not the mode shown above, so the two
            # legitimately disagree (mode "heat", action "idle" -> not running).
            "usage_sensor_active": self._last_usage_active,
            "usage_sensor_last_changed": self._last_usage_changed.isoformat()
            if self._last_usage_changed
            else None,
            "accumulated_seconds": round(self.accumulated_usage_seconds, 2),
        }
