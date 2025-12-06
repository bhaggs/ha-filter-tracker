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
from .utils import async_get_install_datetime

_LOGGER = logging.getLogger(__name__)


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
        # Get all config entries for this domain
        config_entries = self.hass.config_entries.async_entries(DOMAIN)

        if not config_entries:
            self._event = None
            return

        # Find the next upcoming due date
        today = dt_util.now().date()
        upcoming_events = []

        for config_entry in config_entries:
            try:
                # Get filter data
                install_datetime = await async_get_install_datetime(self.hass, config_entry)
                if not install_datetime:
                    continue

                data = config_entry.data
                lifespan_days = data.get(CONF_LIFESPAN_DAYS)
                filter_name = data.get(CONF_NAME)

                # Calculate due date
                due_date = install_datetime.date() + timedelta(days=lifespan_days)

                # Only consider future or today's due dates
                if due_date >= today:
                    upcoming_events.append((due_date, filter_name))
            except Exception as err:
                _LOGGER.warning("Error processing filter entry %s: %s", config_entry.entry_id, err)
                continue

        # Sort by date and get the nearest one
        if upcoming_events:
            upcoming_events.sort()
            next_due_date, next_filter_name = upcoming_events[0]

            self._event = CalendarEvent(
                start=next_due_date,
                end=next_due_date + timedelta(days=1),
                summary=f"{next_filter_name} - Replacement Due",
                description=f"Replace the {next_filter_name} filter",
            )
        else:
            self._event = None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        # Get all config entries for this domain
        config_entries = hass.config_entries.async_entries(DOMAIN)

        if not config_entries:
            return events

        # Convert datetime to date for comparison
        start = start_date.date()
        end = end_date.date()

        for config_entry in config_entries:
            try:
                # Get filter data
                install_datetime = await async_get_install_datetime(hass, config_entry)
                if not install_datetime:
                    continue

                data = config_entry.data
                lifespan_days = data.get(CONF_LIFESPAN_DAYS)
                filter_name = data.get(CONF_NAME)
                filter_type = data.get(CONF_FILTER_TYPE)
                filter_size = data.get(CONF_FILTER_SIZE)

                # Build filter description with optional size
                filter_desc = filter_type
                if filter_size:
                    filter_desc = f"{filter_type} ({filter_size})"

                # Calculate due date
                due_date = install_datetime.date() + timedelta(days=lifespan_days)

                # Check if due date falls within the requested range
                if start <= due_date < end:
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
            except Exception as err:
                _LOGGER.warning("Error processing filter entry %s: %s", config_entry.entry_id, err)
                continue

        # Sort events by start date
        events.sort(key=lambda e: e.start)
        return events
