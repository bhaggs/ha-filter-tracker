"""Base classes for Filter Tracker entities.

Provides shared functionality for device info, install datetime tracking, and
usage-time accounting across the sensor, binary_sensor, and button platforms.

Config changes are deliberately not handled here: an options edit reloads the
config entry, which rebuilds every entity from the new configuration.
"""

from dataclasses import dataclass
from datetime import date, timedelta, datetime
import logging
from typing import Generic, TypeVar

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, Event, State, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_LIFESPAN_DAYS,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
    ATTR_HVAC_ACTION,
    CLIMATE_ACTIVE_ACTIONS,
    CLIMATE_ACTIVE_STATES,
    get_install_update_signal,
    get_usage_update_signal,
)
from .tracker_data import (
    USAGE_SAVE_DELAY_SECONDS,
    async_load_usage_data,
    async_save_usage_data,
)

_LOGGER = logging.getLogger(__name__)

# How often the usage sensor refreshes while its tracked entity is running. Its
# value grows continuously rather than changing on an event, so it needs a tick
# of its own once polling is off. Nothing is written while the entity is idle.
USAGE_REFRESH_INTERVAL = timedelta(minutes=1)


@dataclass
class BaseEntityMeta:
    """Base metadata for filter entities."""
    key: str
    name: str
    device_class: str | None = None
    category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    icon: str | None = None
    unit: str | None = None
    # Long-term statistics are opt-in: without a state_class the recorder keeps
    # only short-term history, so a filter's usage or remaining life cannot be
    # graphed across its lifetime.
    state_class: str | None = None


TMeta = TypeVar('TMeta', bound=BaseEntityMeta)


class BaseFilterEntity(Generic[TMeta]):
    """Base class with shared setup and device info for filter entities.

    Provides:
    - Device info management for unified device grouping
    - Install datetime tracking via dispatcher signals
    - Usage time tracking against a nominated entity
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
        usage_sensor_entity_id: str | None = None,
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
            usage_sensor_entity_id: Binary sensor to track for usage time (optional)
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
        self._usage_sensor_entity_id = usage_sensor_entity_id

        # Usage tracking state
        self._accumulated_usage_seconds: float = 0.0
        self._last_usage_changed: datetime | None = None
        self._last_usage_sensor_state: str = "off"
        self._last_usage_active: bool = False
        self._usage_sensor_available: bool = True

        # Only the usage-time sensor is constructed with a tracked entity, and
        # only it may subscribe to one or write the usage store -- one writer
        # per store, never several racing read-modify-write on one file.
        self._tracks_usage: bool = usage_sensor_entity_id is not None

        # Set common entity attributes
        # Nothing here needs polling. The date-based values change only at
        # midnight and get an explicit refresh; the usage sensor has its own
        # tick. Polling re-derived the same arithmetic for every entity on every
        # scan interval and wrote nothing new.
        self._attr_should_poll = False
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
        if meta.state_class:
            self._attr_state_class = meta.state_class

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher signals when added to hass.

        Config changes are not handled here: an options edit reloads the entry,
        which rebuilds every entity from the new config. Only the button and the
        set_filter_replaced/set_usage_time services push updates into live
        entities, and those are what the signals below carry.
        """
        await super().async_added_to_hass()

        # Subscribe to install datetime updates (if enabled)
        if self._use_install_tracking:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    get_install_update_signal(self._entry_id),
                    self._handle_install_update,
                )
            )

        # Subscribe to usage updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                get_usage_update_signal(self._entry_id),
                self._handle_usage_update,
            )
        )

        # Load usage tracking data and subscribe to sensor state changes
        if self._tracks_usage and self._usage_sensor_entity_id:
            await self._async_load_usage_data()
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._usage_sensor_entity_id],
                    self._async_usage_sensor_state_changed,
                )
            )

            # Always reconcile against the live state, not just for new filters:
            # nothing else corrects a stale stored timestamp after a restart.
            await self._async_reconcile_usage_state()

            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._handle_usage_tick, USAGE_REFRESH_INTERVAL
                )
            )

        # Day-based values (days remaining, life remaining, expired, the due
        # date icon) change only when the local date does.
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_day_rollover, hour=0, minute=0, second=0
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Flush any debounced usage write before going away.

        Usage writes are debounced, which is only safe if removal commits what
        is pending -- otherwise a reload would quietly discard the most recent
        usage.
        """
        await super().async_will_remove_from_hass()
        if self._tracks_usage:
            await self._async_save_usage_data(immediate=True)

    @callback
    def _handle_day_rollover(self, now: datetime) -> None:
        """Re-render at local midnight, when the date-based values change."""
        self.async_write_ha_state()

    @callback
    def _handle_usage_tick(self, now: datetime) -> None:
        """Refresh the usage sensor while its tracked entity is running."""
        if self._last_usage_active:
            self.async_write_ha_state()

    @callback
    def _handle_install_update(self, install_datetime: datetime) -> None:
        """Handle install datetime updates from dispatcher signal.

        Marked as a callback so the dispatcher runs it on the event loop.
        Without it HA treats a plain function as blocking and hands it to an
        executor thread, which is why this used to need the thread-safe
        schedule_update_ha_state.
        """
        self._install_datetime = install_datetime
        self.async_write_ha_state()

    @callback
    def _handle_usage_update(self, usage_data: dict) -> None:
        """Handle usage data updates from dispatcher signal."""
        self._accumulated_usage_seconds = usage_data.get("accumulated_seconds", 0.0)
        self._last_usage_changed = usage_data.get("usage_sensor_last_changed")
        self._last_usage_sensor_state = usage_data.get("last_sensor_state", "off")
        self._last_usage_active = usage_data.get("last_active", False)
        self.async_write_ha_state()

    async def _async_load_usage_data(self) -> None:
        """Load usage tracking data from storage."""
        usage_data = await async_load_usage_data(self.hass, self._entry_id)
        if not usage_data:
            return

        self._accumulated_usage_seconds = usage_data.get("accumulated_seconds", 0.0)
        self._last_usage_changed = usage_data.get("usage_sensor_last_changed")
        self._last_usage_sensor_state = usage_data.get("last_sensor_state", "off")

        # None means the store predates the persisted flag; derive it the way
        # v0.5.0 did so the loaded state is self-consistent. At startup this is
        # superseded moments later by reconciliation against the live state --
        # what protects upgraded installs is accumulated_seconds, which is read
        # unchanged. This matters if the loaded state is ever used before
        # reconciliation runs.
        last_active = usage_data.get("last_active")
        if last_active is None:
            last_active = self._legacy_state_is_active(self._last_usage_sensor_state)
        self._last_usage_active = last_active

    def _state_is_active(self, state: State | None) -> bool:
        """Whether the tracked entity counts as running right now.

        For climate entities the mode is a poor proxy: a thermostat set to
        "heat" sits in hvac_action "idle" most of the time, so counting the mode
        accrues 24/7 for a furnace that ran for an hour. Prefer hvac_action when
        the entity reports it, and fall back to the mode when it does not.
        """
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False

        if state.entity_id.startswith("climate."):
            hvac_action = state.attributes.get(ATTR_HVAC_ACTION)
            if hvac_action is not None:
                return hvac_action in CLIMATE_ACTIVE_ACTIONS
            return state.state in CLIMATE_ACTIVE_STATES

        # binary_sensor, switch, fan, input_boolean
        return state.state == STATE_ON

    def _legacy_state_is_active(self, state_value: str) -> bool:
        """Derive the active flag the way v0.5.0 did.

        Used only for usage stores written before the flag was persisted, so
        existing installs keep their accumulated hours on upgrade.
        """
        if state_value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        if self._usage_sensor_entity_id and self._usage_sensor_entity_id.startswith(
            "climate."
        ):
            return state_value in CLIMATE_ACTIVE_STATES
        return state_value == STATE_ON

    async def _async_reconcile_usage_state(self) -> None:
        """Align tracking state with the tracked entity's live state.

        State changes that happen while HA is down raise no events, and
        async_track_state_change_event does not fire for states that already
        exist when the listener attaches. So a stored "active since T" can be
        arbitrarily stale on startup.

        The elapsed interval is discarded rather than credited: there is no
        evidence about what the entity did while nothing was watching. The
        alternative counted the entire downtime as runtime and kept counting
        until the entity's next real state change, at which point the bogus
        total was committed to storage permanently.
        """
        state = self.hass.states.get(self._usage_sensor_entity_id)

        self._usage_sensor_available = state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )
        self._last_usage_active = self._state_is_active(state)
        self._last_usage_sensor_state = state.state if state else STATE_UNAVAILABLE
        self._last_usage_changed = dt_util.utcnow()

        await self._async_save_usage_data()

        _LOGGER.debug(
            "Reconciled usage tracking for filter %s: %s is %s (%.2f hours accrued)",
            self._name,
            self._usage_sensor_entity_id,
            "active" if self._last_usage_active else "inactive",
            self._accumulated_usage_seconds / 3600,
        )

    async def _async_usage_sensor_state_changed(self, event: Event) -> None:
        """Handle state changes of the tracked usage sensor."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        now = dt_util.utcnow()
        is_active = self._state_is_active(new_state)
        is_available = new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

        # Climate entities fire a state-change event for every attribute update
        # -- current temperature, humidity, preset. Only a change in whether the
        # entity is *running* affects the accounting, so ignore the rest instead
        # of writing storage dozens of times an hour.
        if (
            is_active == self._last_usage_active
            and is_available == self._usage_sensor_available
        ):
            self._last_usage_sensor_state = new_state.state
            return

        if not is_available:
            _LOGGER.warning(
                "Usage sensor %s for filter %s is unavailable, pausing usage tracking",
                self._usage_sensor_entity_id,
                self._name,
            )
        elif not self._usage_sensor_available:
            _LOGGER.info(
                "Usage sensor %s for filter %s is available again",
                self._usage_sensor_entity_id,
                self._name,
            )

        # Credit the interval that just ended, if it was an active one.
        if self._last_usage_active and self._last_usage_changed:
            time_delta = (now - self._last_usage_changed).total_seconds()
            self._accumulated_usage_seconds += time_delta
            _LOGGER.debug(
                "Filter %s accumulated %.2f seconds (total: %.2f hours)",
                self._name,
                time_delta,
                self._accumulated_usage_seconds / 3600,
            )

        self._usage_sensor_available = is_available
        self._last_usage_active = is_active
        self._last_usage_sensor_state = new_state.state
        self._last_usage_changed = now

        await self._async_save_usage_data()
        self.async_write_ha_state()

    async def _async_save_usage_data(self, *, immediate: bool = False) -> None:
        """Save usage tracking data to storage.

        Debounced by default so a cycling fan does not cause a disk write per
        flip; pass immediate=True where the data must be committed now.
        """
        await async_save_usage_data(
            self.hass,
            self._entry_id,
            self._accumulated_usage_seconds,
            self._last_usage_changed,
            self._last_usage_sensor_state,
            self._last_usage_active,
            delay=0 if immediate else USAGE_SAVE_DELAY_SECONDS,
        )

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

    @property
    def usage_sensor_entity_id(self) -> str | None:
        """Return the usage sensor entity ID."""
        return self._usage_sensor_entity_id

    @property
    def accumulated_usage_seconds(self) -> float:
        """Return accumulated usage time in seconds."""
        # If sensor is currently active, include time since last update
        if (
            self._usage_sensor_entity_id
            and self._last_usage_changed
            and self._usage_sensor_available
            and self._last_usage_active
        ):
            time_delta = (dt_util.utcnow() - self._last_usage_changed).total_seconds()
            return self._accumulated_usage_seconds + time_delta
        return self._accumulated_usage_seconds

    @property
    def accumulated_usage_hours(self) -> float:
        """Return accumulated usage time in hours."""
        return self.accumulated_usage_seconds / 3600

    @property
    def usage_sensor_available(self) -> bool:
        """Return whether the usage sensor is available."""
        return self._usage_sensor_available
