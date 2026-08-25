"""Issue #4: an editable, pre-populated install date in the options flow.

Requested as a quality-of-life improvement, but it is also the only way a user
can repair a filter whose date was already corrupted by the bugs in #5, so it
ships alongside that fix.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.util import dt as dt_util

from custom_components.filter_tracker.const import CONF_INSTALL_DATE

from .conftest import setup_fixture, stored_install_datetime


def _schema_default(data_schema: vol.Schema, key: str):
    """Read the default a form field is pre-populated with."""
    for marker in data_schema.schema:
        if marker.schema == key:
            default = marker.default
            return default() if callable(default) else default
    raise AssertionError(f"{key!r} not present in the options form")


def _base_input(fixture: dict) -> dict:
    """The options form's required fields, unchanged from stored config."""
    data = fixture["data"]
    return {
        "name": data["name"],
        "lifespan_amount": data["lifespan_days"],
        "lifespan_unit": "days",
        "filter_type": data["filter_type"],
    }


async def test_options_form_prepopulates_install_date(hass, hass_storage):
    """The picker opens on the filter's current install date."""
    entry, fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    result = await hass.config_entries.options.async_init(entry.entry_id)

    expected = dt_util.as_local(
        dt_util.parse_datetime(fixture["expected_install_datetime"])
    ).date()

    assert _schema_default(result["data_schema"], CONF_INSTALL_DATE) == expected.isoformat()


async def test_changing_install_date_persists_and_updates_entities(hass, hass_storage):
    """Editing the date writes storage and moves the dependent sensors."""
    entry, fixture = await setup_fixture(hass, hass_storage, "calendar_only")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**_base_input(fixture), CONF_INSTALL_DATE: "2026-07-04"},
    )
    await hass.async_block_till_done()

    stored = dt_util.parse_datetime(stored_install_datetime(hass_storage, fixture))
    assert dt_util.as_local(stored).date().isoformat() == "2026-07-04"

    # The due date sensor derives from it: 2026-07-04 + 90 days.
    state = hass.states.get("sensor.living_room_air_purifier_filter_replacement_due_date")
    assert state is not None
    assert dt_util.as_local(dt_util.parse_datetime(state.state)).date().isoformat() == (
        "2026-10-02"
    )


async def test_saving_options_untouched_preserves_install_datetime(hass, hass_storage):
    """A no-op save must not disturb the install datetime at all.

    The picker is date-only but the stored value carries a time (a "Filter
    replaced" press records the moment). Writing unconditionally would silently
    round every options save down to local midnight, so an unchanged date must
    skip the write entirely rather than rewrite the same day.
    """
    entry, fixture = await setup_fixture(
        hass,
        hass_storage,
        "with_usage_sensor",
        initial_states={"fan.furnace_blower": "off"},
    )
    before = stored_install_datetime(hass_storage, fixture)
    assert before == fixture["expected_install_datetime"]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    current = _schema_default(result["data_schema"], CONF_INSTALL_DATE)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            **_base_input(fixture),
            "usage_sensor": fixture["data"]["usage_sensor"],
            CONF_INSTALL_DATE: current,
        },
    )
    await hass.async_block_till_done()

    assert stored_install_datetime(hass_storage, fixture) == before
