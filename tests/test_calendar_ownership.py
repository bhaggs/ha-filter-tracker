"""The shared calendar must survive its owning entry being unloaded.

One calendar serves the whole integration, but HA entities belong to a config
entry, so some entry has to own it. If that entry is reloaded or removed while
other filters remain, the calendar goes with its platforms -- and must come back.
"""

from __future__ import annotations

from .conftest import setup_fixture

CALENDAR = "calendar.filter_tracker"


def _assert_calendar_working(hass, message: str) -> None:
    """The calendar must be present AND live.

    On unload HA keeps the entity and marks it unavailable/restored rather than
    deleting it, so merely existing proves nothing -- a permanently unavailable
    calendar is exactly the failure being guarded against.
    """
    state = hass.states.get(CALENDAR)
    assert state is not None, f"{message} (entity gone)"
    assert state.state != "unavailable", f"{message} (entity stuck unavailable)"


async def test_calendar_survives_reload_of_its_owner(hass, hass_storage):
    """Reloading the entry that created the calendar must recreate it.

    The creation guard was a bare 'already created' flag that only cleared when
    the *last* entry unloaded, so a reload destroyed the calendar permanently.
    """
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")
    _assert_calendar_working(hass, "calendar broken before reload")

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    _assert_calendar_working(hass, "calendar lost by reloading the entry that owns it")


async def test_calendar_survives_owner_reload_with_other_filters(hass, hass_storage):
    """With several filters, reloading the owner must not lose the calendar."""
    owner, _ = await setup_fixture(hass, hass_storage, "calendar_only")
    await setup_fixture(hass, hass_storage, "with_usage_sensor",
                        initial_states={"fan.furnace_blower": "off"})

    _assert_calendar_working(hass, "calendar broken before reload")

    await hass.config_entries.async_reload(owner.entry_id)
    await hass.async_block_till_done()

    _assert_calendar_working(hass, "calendar lost by reloading its owner")


async def test_calendar_rehomes_when_owner_is_removed(hass, hass_storage):
    """Deleting the owning filter must hand the calendar to a surviving one."""
    owner, _ = await setup_fixture(hass, hass_storage, "calendar_only")
    await setup_fixture(hass, hass_storage, "with_usage_sensor",
                        initial_states={"fan.furnace_blower": "off"})

    _assert_calendar_working(hass, "calendar broken before removal")

    await hass.config_entries.async_remove(owner.entry_id)
    await hass.async_block_till_done()

    _assert_calendar_working(hass, "calendar lost when its owning filter was deleted")


async def test_calendar_goes_away_with_the_last_filter(hass, hass_storage):
    """Removing every filter should leave no calendar behind."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CALENDAR) is None
