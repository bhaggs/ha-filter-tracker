"""Upgrade gate: v0.5.0 on-disk state must survive loading on the current code.

This is the regression gate for the whole refactor plan. It is deliberately
written against observable outcomes -- storage contents, entity registry entries,
config entry data -- and never against integration internals, so it keeps working
across the reload-pattern conversion and the base-class refactor.

Run it after every phase. Any diff here is a blocker, not a fixup.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.filter_tracker.const import DOMAIN

from .conftest import (
    setup_fixture,
    stored_accumulated_seconds,
    stored_install_datetime,
)

ALL_FIXTURES = ["calendar_only", "with_usage_sensor", "lingering_temp_key"]

# Frozen forever: unique_id is f"{entry_id}_{meta.key}". Renaming any of these
# orphans the user's existing entity and silently drops its recorder history
# plus every dashboard and automation reference.
FROZEN_META_KEYS = {
    "install_date",
    "due_date",
    "days_remaining",
    "life_remaining_percent",
    "filter_type",
    "usage_time",
    "expired",
    "reset_install_date",
}


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_entry_loads(hass, hass_storage, fixture_name):
    """Every v0.5.0 shape still sets up."""
    entry, _ = await setup_fixture(hass, hass_storage, fixture_name)
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_install_datetime_preserved_exactly(hass, hass_storage, fixture_name):
    """The stored install datetime is byte-identical after setup.

    'Byte-identical' rather than 'recent' is the whole point: the C1/C2 bugs
    produce a perfectly plausible-looking datetime, just the wrong one.
    """
    _, fixture = await setup_fixture(hass, hass_storage, fixture_name)

    assert stored_install_datetime(hass_storage, fixture) == fixture[
        "expected_install_datetime"
    ]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_config_data_preserved(hass, hass_storage, fixture_name):
    """User config survives untouched in entry.data.

    Guards against a future move to entry.options, which would make every
    deployed filter read as unconfigured.
    """
    entry, fixture = await setup_fixture(hass, hass_storage, fixture_name)

    for key, value in fixture["data"].items():
        if key == "_temp_storage_key":
            # Legitimately cleaned up once H4 is fixed; not user config.
            continue
        assert entry.data.get(key) == value, f"config key {key!r} changed"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_unique_ids_stable(hass, hass_storage, fixture_name):
    """Every v0.5.0 unique_id still exists, and nothing duplicates it.

    A changed unique_id is invisible in normal use -- HA simply registers a new
    entity alongside the orphan -- so it needs an explicit assertion.
    """
    entry, fixture = await setup_fixture(hass, hass_storage, fixture_name)

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    # The shared calendar is owned by whichever entry created it and is not
    # per-filter; it has its own stability test below.
    actual = {e.unique_id for e in entries if e.domain != "calendar"}

    expected = set(fixture["expected_unique_ids"])
    missing = expected - actual
    assert not missing, f"unique_ids disappeared (orphaning user entities): {missing}"

    # Anything extra must still be a known key, never a rename of an existing one.
    for unique_id in actual - expected:
        suffix = unique_id.removeprefix(f"{entry.entry_id}_")
        assert suffix in FROZEN_META_KEYS, f"unexpected new unique_id {unique_id!r}"


async def test_accumulated_usage_preserved(hass, hass_storage):
    """Usage hours survive the upgrade exactly.

    Also guards against a USAGE_STORE_VERSION bump landing without an
    async_migrate_func, which would silently read the old file as empty.
    """
    _, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(
        fixture["expected_accumulated_seconds"]
    )


async def test_calendar_unique_id_stable(hass, hass_storage):
    """The shared calendar keeps its unique_id, so existing cards keep working."""
    await setup_fixture(hass, hass_storage, "calendar_only")

    registry = er.async_get(hass)
    calendar_ids = {
        e.unique_id
        for e in registry.entities.values()
        if e.platform == DOMAIN and e.domain == "calendar"
    }

    assert calendar_ids == {f"{DOMAIN}_calendar"}
