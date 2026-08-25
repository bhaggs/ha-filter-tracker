"""The calendar must reflect install-date changes from every write path.

The calendar reads shared in-memory state rather than storage, so every code
path that changes the install date has to keep that state in step. Missing one
leaves the calendar silently showing a stale due date until the next reload.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.filter_tracker.const import (
    ATTR_ENTRY_ID,
    ATTR_REPLACEMENT_DATETIME,
    DOMAIN,
    SERVICE_SET_FILTER_REPLACED,
)

from .conftest import setup_fixture

CALENDAR = "calendar.filter_tracker"


async def _next_due_date(hass) -> str | None:
    """Advance past a calendar poll and read the next due date it reports."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=120))
    await hass.async_block_till_done()

    state = hass.states.get(CALENDAR)
    assert state is not None, "calendar entity missing"
    start = state.attributes.get("start_time")
    return start.split(" ")[0] if start else None


async def test_calendar_reflects_service_install_date_change(hass, hass_storage):
    """set_filter_replaced must move the calendar's due date."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    # Baseline: install 2026-06-01 + 90 days.
    assert await _next_due_date(hass) == "2026-08-30"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_REPLACED,
        {
            ATTR_ENTRY_ID: entry.entry_id,
            ATTR_REPLACEMENT_DATETIME: "2026-08-20 12:00:00",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    # 2026-08-20 + 90 days.
    assert await _next_due_date(hass) == "2026-11-18"


async def test_calendar_reflects_button_install_date_change(hass, hass_storage):
    """Pressing "Filter replaced" must move the calendar's due date."""
    await setup_fixture(hass, hass_storage, "calendar_only")

    assert await _next_due_date(hass) == "2026-08-30"

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.living_room_air_purifier_filter_replaced"},
        blocking=True,
    )
    await hass.async_block_till_done()

    expected = (dt_util.now().date() + timedelta(days=90)).isoformat()
    assert await _next_due_date(hass) == expected
