"""Behaviour the options flow must preserve.

Characterisation tests for the config-update path. They are written to pass
both before and after the conversion from bespoke dispatcher signals to Home
Assistant's standard update-listener/reload pattern -- that is the point: the
refactor deletes ~90 lines and must not change a single observable outcome.

Everything here is asserted through entity states, the device registry, and
storage. Nothing touches dispatcher internals, which the refactor removes.
"""

from __future__ import annotations

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.filter_tracker.const import CONF_INSTALL_DATE, DOMAIN

from .conftest import (
    setup_fixture,
    submit_options,
    stored_accumulated_seconds,
    stored_install_datetime,
)


async def test_lifespan_change_moves_due_date(hass, hass_storage):
    """Editing the lifespan must move the due date sensor."""
    entry, fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    # install 2026-06-01 + 90 days
    due = hass.states.get("sensor.living_room_air_purifier_filter_replacement_due_date")
    assert dt_util.as_local(dt_util.parse_datetime(due.state)).date().isoformat() == (
        "2026-08-30"
    )

    await submit_options(hass, entry, lifespan_amount=180, lifespan_unit="days")

    due = hass.states.get("sensor.living_room_air_purifier_filter_replacement_due_date")
    assert dt_util.as_local(dt_util.parse_datetime(due.state)).date().isoformat() == (
        "2026-11-28"
    ), "due date did not follow the lifespan change"


async def test_name_change_updates_device(hass, hass_storage):
    """Renaming a filter must rename its device."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    await submit_options(hass, entry, name="Hallway Purifier")

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert device is not None
    assert device.name == "Hallway Purifier"


async def test_filter_metadata_change_updates_device_model(hass, hass_storage):
    """Type and size feed the device model string."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    await submit_options(hass, entry, filter_type="MERV13", filter_size="20x25x1")

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert device.model == "MERV13 (20x25x1)"


async def test_adding_usage_sensor_creates_usage_entity(hass, hass_storage):
    """A filter with no usage sensor gains one when the option is set."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")
    hass.states.async_set("fan.purifier", "off")

    assert hass.states.get("sensor.living_room_air_purifier_usage_time") is None

    await submit_options(hass, entry, usage_sensor="fan.purifier")

    assert hass.states.get("sensor.living_room_air_purifier_usage_time") is not None, (
        "usage time entity was not created when a usage sensor was added"
    )


async def test_removing_usage_sensor_removes_usage_entity(hass, hass_storage):
    """Clearing the usage sensor removes the usage time entity."""
    entry, _ = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )
    assert hass.states.get("sensor.furnace_filter_usage_time") is not None

    await submit_options(hass, entry, usage_sensor=None)

    state = hass.states.get("sensor.furnace_filter_usage_time")
    assert state is None or state.state == "unavailable", (
        "usage time entity survived removing the usage sensor"
    )


async def test_options_change_preserves_stored_data(hass, hass_storage):
    """No options edit may cost the user their install date or usage hours.

    The reload conversion makes every options save unload and set the entry up
    again, which is exactly the path that used to wipe both stores.
    """
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    await submit_options(hass, entry, name="Renamed Furnace Filter")

    assert stored_install_datetime(hass_storage, fixture) == fixture[
        "expected_install_datetime"
    ]
    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(
        fixture["expected_accumulated_seconds"]
    )


async def test_options_change_keeps_unique_ids(hass, hass_storage):
    """An options edit must not orphan and recreate entities."""
    entry, fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    registry = er.async_get(hass)
    before = {
        e.unique_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    await submit_options(hass, entry, name="Renamed")

    after = {
        e.unique_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert before == after


async def test_config_still_lives_in_entry_data(hass, hass_storage):
    """Config must stay in entry.data, where every deployed install has it.

    Moving to entry.options is the conventional shape, but would make every
    existing filter read as unconfigured without a version bump and migration.
    """
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    await submit_options(hass, entry, name="Still In Data")

    assert entry.data.get("name") == "Still In Data"
    assert entry.data.get("lifespan_days") == 90
