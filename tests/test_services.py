"""The two services: targeting rules, usage adjustment, and availability."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.filter_tracker.const import (
    ATTR_ADJUST_HOURS,
    ATTR_DEVICE_ID,
    ATTR_ENTRY_ID,
    ATTR_USAGE_HOURS,
    DOMAIN,
    SERVICE_SET_FILTER_REPLACED,
    SERVICE_SET_USAGE_TIME,
)

from .conftest import setup_fixture, stored_accumulated_seconds


async def test_services_are_registered(hass, hass_storage):
    """Both services exist once a filter is set up."""
    await setup_fixture(hass, hass_storage, "calendar_only")

    assert hass.services.has_service(DOMAIN, SERVICE_SET_FILTER_REPLACED)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_USAGE_TIME)


async def test_services_survive_unloading_a_filter(hass, hass_storage):
    """Removing a filter must not deregister the services.

    Automations reference services by name; making them vanish because the last
    filter was unloaded breaks those silently.
    """
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SET_FILTER_REPLACED)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_USAGE_TIME)


async def test_cannot_target_both_entry_and_device(hass, hass_storage):
    """entry_id and device_id are alternatives, not a pair."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_REPLACED,
            {ATTR_ENTRY_ID: entry.entry_id, ATTR_DEVICE_ID: "abc123"},
            blocking=True,
        )


async def test_cannot_set_and_adjust_usage_together(hass, hass_storage):
    """usage_hours sets an absolute value; adjust_hours is relative."""
    entry, _ = await setup_fixture(
        hass, hass_storage, "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_USAGE_TIME,
            {
                ATTR_ENTRY_ID: entry.entry_id,
                ATTR_USAGE_HOURS: 10,
                ATTR_ADJUST_HOURS: 5,
            },
            blocking=True,
        )


async def test_set_usage_hours_absolute(hass, hass_storage):
    """usage_hours replaces the accumulated total."""
    entry, fixture = await setup_fixture(
        hass, hass_storage, "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_USAGE_TIME,
        {ATTR_ENTRY_ID: entry.entry_id, ATTR_USAGE_HOURS: 100},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert stored_accumulated_seconds(hass_storage, fixture) == pytest.approx(360000)


async def test_adjust_usage_hours_is_relative_and_clamped(hass, hass_storage):
    """adjust_hours moves the total, and never below zero."""
    entry, fixture = await setup_fixture(
        hass, hass_storage, "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_USAGE_TIME,
        {ATTR_ENTRY_ID: entry.entry_id, ATTR_ADJUST_HOURS: -100000},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert stored_accumulated_seconds(hass_storage, fixture) == 0.0


async def test_set_usage_time_rejects_calendar_only_filter(hass, hass_storage):
    """A filter with no tracked entity has no usage time to set."""
    entry, _ = await setup_fixture(hass, hass_storage, "calendar_only")

    with pytest.raises(HomeAssistantError, match="usage sensor"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_USAGE_TIME,
            {ATTR_ENTRY_ID: entry.entry_id, ATTR_USAGE_HOURS: 5},
            blocking=True,
        )


async def test_unknown_entry_is_rejected(hass, hass_storage):
    """A target that isn't a Filter Tracker entry is an error, not a no-op."""
    await setup_fixture(hass, hass_storage, "calendar_only")

    with pytest.raises(HomeAssistantError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_REPLACED,
            {ATTR_ENTRY_ID: "does-not-exist"},
            blocking=True,
        )
