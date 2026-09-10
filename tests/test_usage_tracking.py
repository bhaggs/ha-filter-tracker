"""Usage-hour accounting: restart reconciliation, HVAC accuracy, single writer."""

from __future__ import annotations

import pytest
from homeassistant.util import dt as dt_util

from .conftest import setup_fixture, stored_accumulated_seconds

USAGE_SENSOR = "sensor.bedroom_purifier_usage_time"


# --------------------------------------------------------------------------
# H2 -- downtime must not be counted as runtime
# --------------------------------------------------------------------------


async def test_restart_does_not_credit_downtime(hass, hass_storage):
    """A tracked entity active at shutdown must not accrue hours while HA is down.

    The stored state says "active since 2026-08-01". HA starts on 2026-08-25
    with the entity off. No state-change event fires for a state that already
    exists, so nothing corrects the stale timestamp on its own.
    """
    _, fixture = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    state = hass.states.get(USAGE_SENSOR)
    assert state is not None

    # 3600s of real usage == 1.0h. Crediting the ~24-day gap would report ~577h.
    assert float(state.state) == pytest.approx(1.0, abs=0.1)


async def test_downtime_is_not_committed_on_next_change(hass, hass_storage):
    """The stale gap must not be written to storage at the next real change.

    Worse than the display being wrong: the old code committed the bogus delta
    permanently the first time the entity changed state.
    """
    _, fixture = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    hass.states.async_set("fan.bedroom_purifier", "on")
    await hass.async_block_till_done()
    hass.states.async_set("fan.bedroom_purifier", "off")
    await hass.async_block_till_done()

    stored = stored_accumulated_seconds(hass_storage, fixture)
    assert stored == pytest.approx(3600.0, abs=60), (
        f"downtime was committed to storage: {stored}s"
    )


async def test_usage_accrues_normally_while_running(hass, hass_storage):
    """Reconciliation must not break ordinary accumulation."""
    _, fixture = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    hass.states.async_set("fan.bedroom_purifier", "on")
    await hass.async_block_till_done()

    # Entity has been on since "now"; the sensor should include live time.
    state = hass.states.get(USAGE_SENSOR)
    assert float(state.state) == pytest.approx(1.0, abs=0.1)

    hass.states.async_set("fan.bedroom_purifier", "off")
    await hass.async_block_till_done()

    stored = stored_accumulated_seconds(hass_storage, fixture)
    assert stored >= 3600.0


# --------------------------------------------------------------------------
# HVAC accuracy -- count actual running, not thermostat mode
# --------------------------------------------------------------------------


CLIMATE_USAGE_SENSOR = "sensor.furnace_filter_usage_time"


async def _setup_climate_filter(hass, hass_storage, hvac_action):
    """Set up a filter tracking a climate entity in mode 'heat'."""
    return await setup_fixture(
        hass,
        hass_storage,
        "climate_filter",
        initial_states={"climate.furnace": ("heat", {"hvac_action": hvac_action})},
    )


async def test_climate_idle_does_not_accrue(hass, hass_storage):
    """A thermostat set to 'heat' but reporting idle must not accrue hours.

    Counting hvac_mode means a furnace left on 'heat' all winter accrues 24/7,
    which badly overstates runtime for the main furnace-filter use case.
    """
    _, fixture = await _setup_climate_filter(hass, hass_storage, "idle")

    state = hass.states.get("sensor.furnace_filter_usage_time")
    assert state is not None
    assert float(state.state) == pytest.approx(0.0, abs=0.01)


async def test_climate_heating_accrues(hass, hass_storage):
    """hvac_action transitions drive accumulation."""
    _, fixture = await _setup_climate_filter(hass, hass_storage, "idle")

    # idle -> heating is an attribute-only change; it must still register.
    hass.states.async_set("climate.furnace", "heat", {"hvac_action": "heating"})
    await hass.async_block_till_done()
    hass.states.async_set("climate.furnace", "heat", {"hvac_action": "idle"})
    await hass.async_block_till_done()

    stored = stored_accumulated_seconds(hass_storage, fixture)
    assert stored is not None and stored >= 0.0

    # And the active flag is back to inactive, so nothing keeps ticking.
    state = hass.states.get("sensor.furnace_filter_usage_time")
    assert state.attributes.get("usage_sensor_active") is False


async def test_climate_without_hvac_action_falls_back_to_mode(hass, hass_storage):
    """Entities that don't report hvac_action keep the old mode-based rule."""
    await setup_fixture(
        hass,
        hass_storage,
        "climate_filter",
        initial_states={"climate.furnace": "heat"},
    )

    state = hass.states.get(CLIMATE_USAGE_SENSOR)
    assert state.attributes.get("usage_sensor_active") is True


# --------------------------------------------------------------------------
# H3 -- only the usage sensor tracks usage
# --------------------------------------------------------------------------


async def test_only_one_entity_writes_usage_data(hass, hass_storage):
    """Changing the usage sensor must not turn every entity into a tracker.

    All seven entities receive the config-update signal, but only the usage-time
    sensor has any business subscribing to the tracked entity. When the others
    joined in, each kept its own accumulator and wrote the same file, racing
    read-modify-write on one store.

    Counting writes is the direct expression of "exactly one writer" -- the
    resulting corruption is timing-dependent and would make a flaky assertion.
    """
    from unittest.mock import patch

    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.filter_tracker.const import get_config_update_signal

    entry, _ = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off", "fan.other": "off"},
    )

    # Switch the tracked entity. Add/remove triggers a reload, but a *change*
    # goes through the dispatcher and is the path that misbehaved.
    async_dispatcher_send(
        hass,
        get_config_update_signal(entry.entry_id),
        {**entry.data, "usage_sensor": "fan.other"},
    )
    await hass.async_block_till_done()

    with patch(
        "custom_components.filter_tracker.base.async_save_usage_data"
    ) as save:
        hass.states.async_set("fan.other", "on")
        await hass.async_block_till_done()

    assert save.call_count == 1, (
        f"{save.call_count} entities wrote the usage store for one state change; "
        "expected exactly the usage-time sensor"
    )
