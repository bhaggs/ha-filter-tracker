"""Smoke test: the integration sets up at all on the pinned HA version."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState

from .conftest import setup_fixture


async def test_entry_sets_up(hass, hass_storage):
    """A v0.5.0 calendar-only filter loads and produces entities."""
    entry, _fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    assert entry.state is ConfigEntryState.LOADED

    states = [s for s in hass.states.async_all() if "purifier" in s.entity_id]
    assert states, f"no entities created; got {[s.entity_id for s in hass.states.async_all()]}"
