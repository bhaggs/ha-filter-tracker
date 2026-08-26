"""Shared fixtures for the filter_tracker test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.filter_tracker.const import DOMAIN

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/filter_tracker loadable in every test."""
    return


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """Entities schedule timers that outlive teardown; don't fail the suite on it."""
    return True


def load_fixture(name: str) -> dict[str, Any]:
    """Load a golden on-disk snapshot from tests/fixtures/v0_5_0."""
    return json.loads((FIXTURE_DIR / "v0_5_0" / f"{name}.json").read_text())


def seed_storage(hass_storage: dict[str, Any], fixture: dict[str, Any]) -> None:
    """Seed hass_storage with a fixture's .storage payloads.

    Mirrors the on-disk envelope HA's Store writes, so the integration reads
    these exactly as it would read a real v0.5.0 user's files.
    """
    for key, data in fixture["storage"].items():
        hass_storage[key] = {
            "version": 1,
            "minor_version": 1,
            "key": key,
            "data": data,
        }


def build_entry(fixture: dict[str, Any]) -> MockConfigEntry:
    """Build a config entry in the exact shape v0.5.0 wrote it.

    v0.5.0 stored all config in ``data`` and left ``options`` empty; keeping that
    shape here is what makes the upgrade assertions meaningful.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title=fixture["title"],
        data=fixture["data"],
        options={},
        entry_id=fixture["entry_id"],
        version=fixture.get("version", 1),
    )


async def setup_fixture(
    hass,
    hass_storage,
    name: str,
    initial_states: dict[str, str] | None = None,
):
    """Seed a golden fixture, set the entry up, and return (entry, fixture).

    ``initial_states`` is applied before setup so a tracked usage entity already
    exists when entities attach their listeners -- matching what a real restart
    looks like, where states are restored before the integration loads. Values
    are either a state string or a ``(state, attributes)`` tuple, the latter for
    climate entities that report ``hvac_action``.
    """
    fixture = load_fixture(name)
    seed_storage(hass_storage, fixture)

    for entity_id, value in (initial_states or {}).items():
        if isinstance(value, tuple):
            state, attributes = value
        else:
            state, attributes = value, None
        hass.states.async_set(entity_id, state, attributes)

    entry = build_entry(fixture)
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry, fixture


def install_key(fixture: dict[str, Any]) -> str:
    """Storage key holding the permanent install datetime for a fixture."""
    return f"{DOMAIN}_{fixture['entry_id']}_install"


def usage_key(fixture: dict[str, Any]) -> str:
    """Storage key holding the usage data for a fixture."""
    return f"{DOMAIN}_{fixture['entry_id']}_usage"


def stored_install_datetime(hass_storage: dict[str, Any], fixture: dict[str, Any]):
    """Read back the persisted install datetime string, or None if absent."""
    record = hass_storage.get(install_key(fixture))
    if not record:
        return None
    return record["data"].get("install_datetime")


def stored_accumulated_seconds(hass_storage: dict[str, Any], fixture: dict[str, Any]):
    """Read back the persisted accumulated usage seconds, or None if absent."""
    record = hass_storage.get(usage_key(fixture))
    if not record:
        return None
    return record["data"].get("accumulated_seconds")
