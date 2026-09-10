"""Phase 4: stop polling for values that change once a day, and stop writing
storage once per tracked-entity toggle.

Every entity was polled on the platform scan interval, re-deriving values that
only change at midnight, and every flip of the tracked entity wrote the usage
store synchronously.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import setup_fixture, stored_accumulated_seconds

USAGE_SENSOR = "sensor.bedroom_purifier_usage_time"
DAYS_REMAINING = "sensor.living_room_air_purifier_filter_life_days_remaining"


async def _advance(hass, freezer, **delta):
    """Move the frozen clock and let any due timers fire."""
    freezer.move_to(dt_util.utcnow() + timedelta(**delta))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_entities_do_not_poll(hass, hass_storage):
    """Nothing should be polled: the values change on a schedule we control.

    Polling re-derived date arithmetic for every entity every scan interval.
    Day-boundary values get an explicit midnight refresh instead, and the usage
    sensor its own interval, so polling buys nothing.
    """
    entry, _ = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    registry = er.async_get(hass)
    polling = []
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "calendar":
            # CalendarEntity is polled by design; it is cheap now that it reads
            # in-memory state rather than storage.
            continue
        obj = hass.data["entity_components"][entity.domain].get_entity(entity.entity_id)
        if obj is not None and obj.should_poll:
            polling.append(entity.entity_id)

    assert not polling, f"entities still polling: {polling}"


async def test_day_rollover_updates_days_remaining(hass, hass_storage, frozen_time):
    """Crossing midnight must still move the day-based sensors.

    This is what polling was doing by accident; without a replacement the
    sensors would freeze until something else happened to write their state.
    """
    await setup_fixture(hass, hass_storage, "calendar_only")

    # install 2026-06-01 + 90 days = due 2026-08-30, frozen "today" 2026-08-25
    assert hass.states.get(DAYS_REMAINING).state == "5"

    await _advance(hass, frozen_time, days=1)

    assert hass.states.get(DAYS_REMAINING).state == "4", (
        "days remaining did not update after the day rolled over"
    )


async def test_usage_sensor_advances_while_active(hass, hass_storage, frozen_time):
    """The usage sensor still ticks up while the tracked entity is running.

    Its value grows continuously, so it was only ever correct *because* of
    polling. Removing polling without a replacement would freeze it.
    """
    await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "on"},
    )

    assert float(hass.states.get(USAGE_SENSOR).state) == 1.0

    await _advance(hass, frozen_time, hours=1)

    assert float(hass.states.get(USAGE_SENSOR).state) == 2.0, (
        "usage sensor stopped advancing without polling"
    )


async def test_idle_usage_sensor_does_not_rewrite_state(hass, hass_storage, frozen_time):
    """An idle filter must not write state on every tick.

    Nothing is accruing, so a write would be pure recorder noise -- the point of
    dropping polling in the first place.
    """
    await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    before = hass.states.get(USAGE_SENSOR).last_updated

    await _advance(hass, frozen_time, hours=1)

    assert hass.states.get(USAGE_SENSOR).last_updated == before, (
        "idle usage sensor rewrote its state"
    )


async def test_rapid_toggles_coalesce_storage_writes(hass, hass_storage, frozen_time):
    """A cycling fan must not cause one disk write per flip."""
    _, fixture = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    usage_key = f"filter_tracker_{fixture['entry_id']}_usage"
    writes = []
    installed = storage.Store._async_write_data

    async def counting_write(store, data_to_write):
        if store.key == usage_key:
            writes.append(store.key)
        await installed(store, data_to_write)

    # hass_storage already patched this with an autospec mock, so wrap it as a
    # plain function rather than trying to autospec a Mock.
    with patch(
        "homeassistant.helpers.storage.Store._async_write_data",
        new=counting_write,
    ):
        for _ in range(10):
            hass.states.async_set("fan.bedroom_purifier", "on")
            await hass.async_block_till_done()
            hass.states.async_set("fan.bedroom_purifier", "off")
            await hass.async_block_till_done()

        during = len(writes)
        await _advance(hass, frozen_time, minutes=5)

    # 20 flips previously meant 20 synchronous writes; debouncing collapses the
    # whole burst into one deferred write.
    assert during <= 2, f"{during} disk writes during 20 state flips"
    assert writes, "usage data was never written at all -- debounce swallowed it"


async def test_pending_usage_write_survives_reload(hass, hass_storage, frozen_time):
    """A deferred write must be flushed before the entity goes away.

    Debouncing writes is only safe if unloading commits what is pending;
    otherwise a reload would quietly discard the most recent usage.
    """
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "usage_active_at_shutdown",
        initial_states={"fan.bedroom_purifier": "off"},
    )

    hass.states.async_set("fan.bedroom_purifier", "on")
    await hass.async_block_till_done()
    freezer_target = dt_util.utcnow() + timedelta(hours=2)
    frozen_time.move_to(freezer_target)
    hass.states.async_set("fan.bedroom_purifier", "off")
    await hass.async_block_till_done()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    stored = stored_accumulated_seconds(hass_storage, fixture)
    assert stored >= 3600 + 7200 - 60, (
        f"usage accrued before the reload was lost: {stored}s"
    )


async def test_sensors_declare_state_class(hass, hass_storage):
    """Long-term statistics need a state_class.

    Without one the recorder keeps only short-term history, so usage hours and
    remaining life can't be graphed over the life of a filter -- which is most
    of the point of tracking them.
    """
    await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    expected = {
        "sensor.furnace_filter_usage_time": "total_increasing",
        "sensor.furnace_filter_filter_life_remaining": "measurement",
        "sensor.furnace_filter_filter_life_days_remaining": "measurement",
    }
    for entity_id, state_class in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} missing"
        assert state.attributes.get("state_class") == state_class, (
            f"{entity_id} has state_class {state.attributes.get('state_class')!r}"
        )
