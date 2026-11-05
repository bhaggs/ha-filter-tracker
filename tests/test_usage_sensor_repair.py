"""The repair issue raised when a filter's usage sensor no longer exists.

Usage hours silently stopped counting when the tracked entity was deleted or
renamed. A rename is now followed; anything that leaves the filter tracking an
entity that isn't there raises a repair issue, which clears when it comes back.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.filter_tracker.const import (
    CONF_USAGE_SENSOR,
    DOMAIN,
    get_missing_usage_sensor_issue_id,
)

from .conftest import setup_fixture, submit_options

TRACKED = "fan.furnace_blower"
USAGE = "sensor.furnace_filter_usage_time"


def issue(hass, entry):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, get_missing_usage_sensor_issue_id(entry.entry_id)
    )


def register_tracked(hass, entity_id: str = TRACKED) -> er.RegistryEntry:
    """Register the tracked entity, as an integration with unique IDs would."""
    domain, object_id = entity_id.split(".")
    return er.async_get(hass).async_get_or_create(
        domain, "test", object_id, suggested_object_id=object_id
    )


async def test_missing_sensor_raises_issue(hass, hass_storage):
    """A usage sensor with neither a registry entry nor a state is missing."""
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")

    found = issue(hass, entry)
    assert found is not None
    assert found.severity == ir.IssueSeverity.WARNING
    assert not found.is_fixable
    assert found.translation_key == "missing_usage_sensor"
    assert found.translation_placeholders == {
        "filter": "Furnace Filter",
        "entity_id": TRACKED,
    }


async def test_state_appearing_clears_issue(hass, hass_storage):
    """An unregistered entity coming back clears the issue on its own."""
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")
    assert issue(hass, entry) is not None

    hass.states.async_set(TRACKED, "off")
    await hass.async_block_till_done()

    assert issue(hass, entry) is None


async def test_registered_sensor_without_state_is_not_missing(hass, hass_storage):
    """A registered entity with no state is reloading or still starting."""
    register_tracked(hass)
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")

    assert issue(hass, entry) is None


async def test_present_sensor_clears_leftover_issue(hass, hass_storage):
    """An issue persisted by an earlier run goes once the sensor checks out."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        get_missing_usage_sensor_issue_id("aaaabbbbccccddddeeeeffff00001111"),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="missing_usage_sensor",
    )
    entry, _ = await setup_fixture(
        hass, hass_storage, "with_usage_sensor", initial_states={TRACKED: "off"}
    )
    assert entry.entry_id == "aaaabbbbccccddddeeeeffff00001111"

    assert issue(hass, entry) is None


async def test_waits_for_startup(hass, hass_storage):
    """At boot the tracked entity's integration may not have loaded yet."""
    hass.set_state(CoreState.not_running)
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")
    assert issue(hass, entry) is None

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert issue(hass, entry) is not None


async def test_deleting_registered_sensor_raises_issue(hass, hass_storage):
    """Removing the tracked entity from the registry raises the issue."""
    register_tracked(hass)
    entry, _ = await setup_fixture(
        hass, hass_storage, "with_usage_sensor", initial_states={TRACKED: "off"}
    )
    assert issue(hass, entry) is None

    er.async_get(hass).async_remove(TRACKED)
    await hass.async_block_till_done()

    assert issue(hass, entry) is not None


async def test_disabling_raises_and_enabling_clears(hass, hass_storage):
    """A disabled entity has no state to count, so it is reported too."""
    register_tracked(hass)
    entry, _ = await setup_fixture(
        hass, hass_storage, "with_usage_sensor", initial_states={TRACKED: "off"}
    )
    registry = er.async_get(hass)

    registry.async_update_entity(TRACKED, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    assert issue(hass, entry) is not None

    registry.async_update_entity(TRACKED, disabled_by=None)
    await hass.async_block_till_done()
    assert issue(hass, entry) is None


async def test_rename_is_followed(hass, hass_storage, frozen_time):
    """Renaming the tracked entity updates the filter instead of losing it."""
    register_tracked(hass)
    entry, fixture = await setup_fixture(
        hass, hass_storage, "with_usage_sensor", initial_states={TRACKED: "off"}
    )
    before = float(hass.states.get(USAGE).state)
    renamed = "fan.attic_blower"

    er.async_get(hass).async_update_entity(TRACKED, new_entity_id=renamed)
    hass.states.async_remove(TRACKED)
    hass.states.async_set(renamed, "off")
    await hass.async_block_till_done()

    assert entry.data[CONF_USAGE_SENSOR] == renamed
    assert issue(hass, entry) is None
    assert float(hass.states.get(USAGE).state) == pytest.approx(before)

    # Hours accrue from the new entity ID.
    hass.states.async_set(renamed, "on")
    await hass.async_block_till_done()
    frozen_time.tick(timedelta(hours=2))
    hass.states.async_set(renamed, "off")
    await hass.async_block_till_done()

    assert float(hass.states.get(USAGE).state) == pytest.approx(before + 2, abs=0.01)


async def test_clearing_usage_sensor_removes_issue(hass, hass_storage):
    """Choosing no usage sensor resolves the issue."""
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")
    assert issue(hass, entry) is not None

    await submit_options(hass, entry, usage_sensor=None)

    assert issue(hass, entry) is None


async def test_choosing_another_sensor_removes_issue(hass, hass_storage):
    """Pointing the filter at an entity that exists resolves the issue."""
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")
    assert issue(hass, entry) is not None
    hass.states.async_set("switch.purifier", "off")

    await submit_options(hass, entry, usage_sensor="switch.purifier")

    assert issue(hass, entry) is None


async def test_deleting_filter_removes_issue(hass, hass_storage):
    """The issue doesn't outlive the filter it is about."""
    entry, _ = await setup_fixture(hass, hass_storage, "with_usage_sensor")
    assert issue(hass, entry) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert issue(hass, entry) is None
