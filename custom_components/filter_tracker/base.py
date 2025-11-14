"""Base classes for Filter Tracker entities.

Provides shared functionality for device info, config updates, and install datetime
tracking across sensor, binary_sensor, and button platforms.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Generic, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_LIFESPAN_DAYS,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
    get_install_update_signal,
    get_config_update_signal,
)


@dataclass
class BaseEntityMeta:
    """Base metadata for filter entities."""
    key: str
    name: str
    device_class: str | None = None
    category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    icon: str | None = None
    unit: str | None = None


TMeta = TypeVar('TMeta', bound=BaseEntityMeta)


class BaseFilterEntity(Generic[TMeta]):
    """Base class with shared setup and device info for filter entities.

    Provides:
    - Device info management for unified device grouping
    - Install datetime tracking via dispatcher signals
    - Config update handling via dispatcher signals
    - Shared properties (install_datetime, due_date)

    This class should be used with multiple inheritance:
        class MySensor(BaseFilterEntity[SensorMeta], SensorEntity):
            ...
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        install_datetime: datetime | None,
        name: str,
        lifespan_days: int,
        filter_type: str | None,
        filter_size: str | None,
        manufacturer: str | None,
        meta: TMeta,
        use_install_tracking: bool = True,
    ) -> None:
        """Initialize base filter entity.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            install_datetime: Filter installation datetime (can be None for buttons)
            name: Filter name
            lifespan_days: Filter lifespan in days
            filter_type: Type of filter
            filter_size: Physical dimensions of filter (optional)
            manufacturer: Filter manufacturer (optional)
            meta: Entity metadata (SensorMeta, BinarySensorMeta, or ButtonMeta)
            use_install_tracking: Whether to subscribe to install datetime updates
                                  (False for button entities that produce updates)
        """
        super().__init__()
        self.hass = hass
        self._entry_id = entry_id
        self._install_datetime = install_datetime
        self._name = name
        self._lifespan_days = lifespan_days
        self._filter_type = filter_type or "Generic Filter"
        self._filter_size = filter_size
        self._manufacturer = manufacturer or "Unknown"
        self._use_install_tracking = use_install_tracking
        self._remove_install_listener: Callable[[], None] | None = None
        self._remove_config_listener: Callable[[], None] | None = None

        # Set common entity attributes
        self._attr_unique_id = f"{entry_id}_{meta.key}"
        self._attr_has_entity_name = True
        self._attr_name = meta.name
        self._attr_device_class = meta.device_class
        self._attr_entity_category = meta.category

        # Set sensor-specific attributes (if provided in meta)
        if meta.icon:
            self._attr_icon = meta.icon
        if meta.unit:
            self._attr_native_unit_of_measurement = meta.unit

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher signals when added to hass."""
        await super().async_added_to_hass()

        # Subscribe to install datetime updates (if enabled)
        if self._use_install_tracking:
            install_signal = get_install_update_signal(self._entry_id)
            self._remove_install_listener = async_dispatcher_connect(
                self.hass, install_signal, self._handle_install_update
            )

        # Subscribe to config updates
        config_signal = get_config_update_signal(self._entry_id)
        self._remove_config_listener = async_dispatcher_connect(
            self.hass, config_signal, self._handle_config_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from dispatcher signals when removed from hass."""
        await super().async_will_remove_from_hass()
        if self._remove_install_listener:
            self._remove_install_listener()
            self._remove_install_listener = None
        if self._remove_config_listener:
            self._remove_config_listener()
            self._remove_config_listener = None

    def _handle_install_update(self, install_datetime: datetime) -> None:
        """Handle install datetime updates from dispatcher signal."""
        self._install_datetime = install_datetime
        self.schedule_update_ha_state()

    def _handle_config_update(self, config_data: dict) -> None:
        """Handle config updates from dispatcher signal."""
        # Update internal state
        self._name = config_data.get(CONF_NAME, self._name)
        self._lifespan_days = config_data.get(CONF_LIFESPAN_DAYS, self._lifespan_days)
        self._filter_type = config_data.get(CONF_FILTER_TYPE) or "Generic Filter"
        self._filter_size = config_data.get(CONF_FILTER_SIZE)
        self._manufacturer = config_data.get(CONF_MANUFACTURER) or "Unknown"

        # Build model string with optional size
        model = self._filter_type
        if self._filter_size:
            model = f"{self._filter_type} ({self._filter_size})"

        # Update device registry with new metadata
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, self._entry_id)})
        if device:
            device_registry.async_update_device(
                device.id,
                name=self._name,
                model=model,
                manufacturer=self._manufacturer,
            )

        # Trigger state update for lifespan changes
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group entities under one device."""
        # Build model string with optional size
        model = self._filter_type
        if self._filter_size:
            model = f"{self._filter_type} ({self._filter_size})"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._name,
            model=model,
            manufacturer=self._manufacturer,
        )

    @property
    def install_datetime(self) -> datetime:
        """Return the filter installation datetime."""
        return self._install_datetime

    @property
    def due_date(self) -> date:
        """Calculate and return the filter replacement due date."""
        return self._install_datetime.date() + timedelta(days=self._lifespan_days)
