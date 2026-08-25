"""Calendar platform for Filter Tracker integration.

Provides a calendar view of all filter replacement due dates.
"""

from datetime import datetime, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_LIFESPAN_DAYS,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
)

_LOGGER = logging.getLogger(__name__)


def _iter_filter_due_dates(hass: HomeAssistant):
    """Yield (due_date, config_entry) for every loaded filter.

    Reads only from the in-memory state resolved at setup. The calendar is a
    display surface polled every 60s across every entry; it previously reached
    into storage through a helper that could also write, which turned a failed
    read into an unattended, repeating overwrite of the user's install date.
    """
    for config_entry in hass.config_entries.async_loaded_entries(DOMAIN):
        runtime_data = getattr(config_entry, "runtime_data", None)
        if runtime_data is None:
            continue

        install_datetime = runtime_data.install_datetime
        lifespan_days = config_entry.data.get(CONF_LIFESPAN_DAYS)
        if install_datetime is None or lifespan_days is None:
            continue

        yield install_datetime.date() + timedelta(days=lifespan_days), config_entry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Filter Tracker calendar - creates one calendar for entire integration."""

    # Ensure domain data exists
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    # Only create calendar once across all config entries
    if "calendar_created" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["calendar_created"] = True

        # Create single calendar showing all filters
        calendar = FilterTrackerCalendar(hass)
        async_add_entities([calendar])
        _LOGGER.debug("Created integration-level Filter Tracker calendar")
    else:
        _LOGGER.debug("Calendar already exists, skipping creation for entry %s", config_entry.entry_id)


class FilterTrackerCalendar(CalendarEntity):
    """Calendar entity showing all filter replacement due dates."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the calendar entity."""
        super().__init__()
        self.hass = hass
        self._attr_name = "Filter Tracker"
        self._attr_unique_id = f"{DOMAIN}_calendar"
        self._attr_has_entity_name = False
        self._event = None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    async def async_update(self) -> None:
        """Update the calendar entity with the next upcoming event."""
        today = dt_util.now().date()

        upcoming_events = [
            (due_date, config_entry.data.get(CONF_NAME))
            for due_date, config_entry in _iter_filter_due_dates(self.hass)
            if due_date >= today
        ]

        if not upcoming_events:
            self._event = None
            return

        upcoming_events.sort()
        next_due_date, next_filter_name = upcoming_events[0]

        self._event = CalendarEvent(
            start=next_due_date,
            end=next_due_date + timedelta(days=1),
            summary=f"{next_filter_name} - Replacement Due",
            description=f"Replace the {next_filter_name} filter",
        )

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        # Convert datetime to date for comparison
        start = start_date.date()
        end = end_date.date()

        for due_date, config_entry in _iter_filter_due_dates(hass):
            if not start <= due_date < end:
                continue

            data = config_entry.data
            filter_name = data.get(CONF_NAME)
            filter_type = data.get(CONF_FILTER_TYPE)
            filter_size = data.get(CONF_FILTER_SIZE)

            # Build filter description with optional size
            filter_desc = filter_type
            if filter_size:
                filter_desc = f"{filter_type} ({filter_size})"

            events.append(
                CalendarEvent(
                    start=due_date,
                    end=due_date + timedelta(days=1),
                    summary=f"{filter_name} - Replacement Due",
                    description=f"Replace the {filter_name} {filter_desc} filter",
                    location="Home",
                    uid=f"filter_tracker_{config_entry.entry_id}_{due_date.isoformat()}",
                )
            )

        # Sort events by start date
        events.sort(key=lambda e: e.start)
        return events
