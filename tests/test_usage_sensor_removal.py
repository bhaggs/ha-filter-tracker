"""What happens to accumulated hours when the usage sensor is removed.

Worth pinning explicitly: the reset used to live in the config-update handler,
which the reload conversion deleted. Whatever the behaviour is now, the README
has to describe it correctly.
"""

from __future__ import annotations

import pytest

from .conftest import setup_fixture, stored_accumulated_seconds, submit_options


async def test_removing_usage_sensor_keeps_accumulated_hours(hass, hass_storage):
    """Clearing the usage sensor leaves the stored hours intact."""
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )
    before = fixture["expected_accumulated_seconds"]
    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(before)

    await submit_options(hass, entry, usage_sensor=None)

    assert hass.states.get("sensor.furnace_filter_usage_time") is None or (
        hass.states.get("sensor.furnace_filter_usage_time").state == "unavailable"
    )
    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(before)


async def test_readding_usage_sensor_restores_hours(hass, hass_storage):
    """Re-adding a usage sensor brings the previous hours back."""
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )
    before = fixture["expected_accumulated_seconds"]

    await submit_options(hass, entry, usage_sensor=None)
    await submit_options(hass, entry, usage_sensor="fan.furnace_blower")

    state = hass.states.get("sensor.furnace_filter_usage_time")
    assert state is not None
    assert float(state.state) == pytest.approx(before / 3600, abs=0.1)
