"""Regression tests for the two critical data-loss bugs (C1, C2 / issue #5).

These are written to FAIL on the current code and pass once Phase 1 lands.
Each one names the mechanism it pins down, because the symptom -- "the install
date is a plausible but wrong datetime" -- is identical across all of them.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import (
    install_key,
    setup_fixture,
    stored_accumulated_seconds,
    stored_install_datetime,
)


# --------------------------------------------------------------------------
# C1 -- reload wipes storage
# --------------------------------------------------------------------------


async def test_reload_preserves_install_date(hass, hass_storage):
    """Reloading an entry must not destroy the install date.

    async_unload_entry removes the store, but HA runs unload on every reload,
    not just on deletion. The UI reload button, reload_config_entry, and the
    integration's own options flow all hit this.
    """
    entry, fixture = await setup_fixture(hass, hass_storage, "calendar_only")
    expected = fixture["expected_install_datetime"]

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert stored_install_datetime(hass_storage, fixture) == expected


async def test_reload_preserves_usage_hours(hass, hass_storage):
    """Reloading an entry must not zero accumulated usage hours."""
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )
    expected = fixture["expected_accumulated_seconds"]

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(expected)


# --------------------------------------------------------------------------
# C2 -- reads that write
# --------------------------------------------------------------------------


async def test_unreadable_store_does_not_reset_install_date(hass, hass_storage):
    """A corrupt store must never be overwritten with today's date.

    async_load_install_datetime swallows every exception and returns None, and
    the caller treats None as "brand new filter" and persists today. That turns
    one transient read failure into permanent data loss. Failing closed means
    the entity goes unavailable instead -- recoverable, and visible.
    """
    fixture_name = "calendar_only"
    entry, fixture = await setup_fixture(hass, hass_storage, fixture_name)
    key = install_key(fixture)

    # Corrupt the stored payload the way a truncated/garbled file would.
    hass_storage[key]["data"] = {"install_datetime": "not-a-datetime"}

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    stored = stored_install_datetime(hass_storage, fixture)
    today = dt_util.utcnow().date().isoformat()
    assert stored is None or not str(stored).startswith(today), (
        f"unreadable store was silently replaced with today's date ({stored!r})"
    )


async def test_calendar_poll_does_not_repair_corrupt_store(hass, hass_storage):
    """A corrupt store must not be rewritten by an unattended calendar poll.

    This is what makes C2 dangerous rather than merely wrong: the damage needs
    no user action and repeats every 60s, so any window in which the read fails
    is enough to lose the date permanently.
    """
    _, fixture = await setup_fixture(hass, hass_storage, "calendar_only")
    key = install_key(fixture)

    hass_storage[key]["data"] = {"install_datetime": "not-a-datetime"}

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=120))
    await hass.async_block_till_done()

    stored = stored_install_datetime(hass_storage, fixture)
    today = dt_util.utcnow().date().isoformat()
    assert stored is None or not str(stored).startswith(today), (
        f"a calendar poll silently reset the install date to today ({stored!r})"
    )


async def test_calendar_poll_does_not_write_storage(hass, hass_storage):
    """The calendar must never write. It is a read-only view.

    It calls async_get_install_datetime once per entry per 60s poll, and every
    branch of that function can write. Any write from a display path is an
    unattended, repeating corruption vector.
    """
    _, fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    key = install_key(fixture)
    before = dict(hass_storage[key])

    # Advance well past the calendar's 60s scan interval.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=120))
    await hass.async_block_till_done()

    assert hass_storage[key] == before, "a calendar poll wrote to storage"


async def test_lingering_temp_key_does_not_revert_install_date(hass, hass_storage):
    """The issue #5 mechanism.

    When _temp_storage_key is left in entry data (H4), the install date is
    re-migrated from the CREATION-time temp store, overwriting a newer value the
    user set with the 'Filter replaced' button. The user sees their dates snap
    back to an older value after a restart, across every filter at once.
    """
    _, fixture = await setup_fixture(hass, hass_storage, "lingering_temp_key")

    stored = stored_install_datetime(hass_storage, fixture)

    assert stored != fixture["stale_temp_datetime"], (
        "install date reverted to the stale temp-store value (issue #5)"
    )
    assert stored == fixture["expected_install_datetime"]


async def test_removing_entry_still_deletes_storage(hass, hass_storage):
    """Deleting a filter must still clean up its stores.

    The counterpart to test_reload_preserves_install_date: moving cleanup out of
    unload must not turn into never cleaning up, which would leak two .storage
    files per filter the user ever removes.
    """
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert stored_install_datetime(hass_storage, fixture) is None
    assert stored_accumulated_seconds(hass_storage, fixture) is None


async def test_temp_storage_is_cleaned_up(hass, hass_storage):
    """The temp store and its entry-data key must not survive setup.

    One orphaned .storage file per filter ever created leaks otherwise, and the
    lingering key is what arms the reversion bug above.
    """
    entry, fixture = await setup_fixture(hass, hass_storage, "lingering_temp_key")

    assert "_temp_storage_key" not in entry.data
    assert fixture["temp_storage_key"] not in hass_storage
