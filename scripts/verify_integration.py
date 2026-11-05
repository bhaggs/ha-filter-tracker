"""Run the integration against a real, current Home Assistant and check what it does.

The pytest suite runs on whatever Home Assistant pytest-homeassistant-custom-component
pins, which trails releases by days or weeks. This script fills that gap: it
installs nothing of its own, imports the integration into whichever
homeassistant package the interpreter has, brings HA up the way bootstrap.py
does, and asserts on behaviour.

Requires Python 3.14.2 or later (Home Assistant's own floor), and:

    uv venv -p 3.14 /tmp/ha-venv
    uv pip install -p /tmp/ha-venv "homeassistant==2026.11.0"

Run from the repository root:

    /tmp/ha-venv/bin/python scripts/verify_integration.py

Nothing is written to the repository; everything lives in a temp directory.
Exits non-zero if any check fails.
"""
import asyncio
import inspect
import logging
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from homeassistant import loader  # noqa: E402
from homeassistant.config_entries import ConfigEntries  # noqa: E402
from homeassistant.const import STATE_OFF  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import (  # noqa: E402
    area_registry,
    category_registry,
    device_registry as dr,
    entity,
    entity_registry as er,
    floor_registry,
    frame,
    issue_registry,
    label_registry,
)
from homeassistant.helpers.entity_component import DATA_INSTANCES  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402

from custom_components.filter_tracker import (  # noqa: E402
    base,
    binary_sensor,
    button,
    calendar,
    sensor,
)
from custom_components.filter_tracker.const import DOMAIN  # noqa: E402

FAILED: list[str] = []
TMP = tempfile.mkdtemp(prefix="filter_tracker_verify_")
HASSES: list[HomeAssistant] = []

USAGE_SOURCE = "binary_sensor.furnace_running"


def check(label: str, cond: bool, extra: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAILED.append(label)


class ErrorLog(logging.Handler):
    """Collect ERROR records, so a hook that raises can't pass silently.

    Home Assistant catches and logs exceptions from async_entity_id_changed
    rather than propagating them.
    """

    def __init__(self):
        super().__init__(logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


async def new_hass() -> HomeAssistant:
    """A Home Assistant brought up the way bootstrap.py does, minus the HTTP side."""
    hass = HomeAssistant(tempfile.mkdtemp(dir=TMP))
    hass.config.skip_pip = True
    HASSES.append(hass)
    # Without the frame helper, a deprecated HA API called from the integration
    # raises here instead of being reported the way a real install reports it.
    frame.async_setup(hass)
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    dr.async_setup(hass)
    await asyncio.gather(
        area_registry.async_load(hass, load_empty=True),
        category_registry.async_load(hass, load_empty=True),
        dr.async_load(hass, load_empty=True),
        er.async_load(hass, load_empty=True),
        floor_registry.async_load(hass, load_empty=True),
        issue_registry.async_load(hass, load_empty=True),
        label_registry.async_load(hass, load_empty=True),
    )
    await hass.async_start()
    return hass


async def add_filter(hass: HomeAssistant, name: str, usage_sensor: str | None):
    """Create a filter through the real config flow, as the UI does."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    data = {
        "name": name,
        "install_date": "2026-08-01",  # overdue, so a reset is visible
        "lifespan_amount": 3,
        "lifespan_unit": "months",
        "filter_type": "MERV 11",
    }
    if usage_sensor:
        data["usage_sensor"] = usage_sensor
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    await hass.async_block_till_done()
    return result["result"]


def entity_ids(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    """Map each of the entry's unique_id suffixes to its entity_id."""
    return {
        e.unique_id.removeprefix(f"{entry_id}_"): e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    }


def live_entity(hass: HomeAssistant, entity_id: str):
    return hass.data[DATA_INSTANCES][entity_id.split(".")[0]].get_entity(entity_id)


async def rename(hass: HomeAssistant, old: str, new: str) -> None:
    er.async_get(hass).async_update_entity(old, new_entity_id=new)
    await hass.async_block_till_done()


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


async def s1_opt_in_covers_every_entity_class():
    """HA decides per class whether a rename can happen in place."""
    classes = {
        cls
        for module in (base, binary_sensor, button, calendar, sensor)
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, entity.Entity) and cls.__module__ == module.__name__
    }
    check("found the integration's entity classes", len(classes) >= 8, f"{len(classes)} classes")
    for cls in sorted(classes, key=lambda c: c.__name__):
        check(
            f"{cls.__name__} renames in place",
            not entity._entity_class_requires_readd(cls),
        )

    # The control: a custom class with a lifecycle hook and no opt-in must still
    # be re-added, or the checks above prove nothing.
    class NotOptedIn(entity.Entity):
        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()

    check(
        "control: a class that does not opt in is re-added",
        entity._entity_class_requires_readd(NotOptedIn),
    )


async def _rename_scenario(hass: HomeAssistant, errors: ErrorLog, *, opted_in: bool):
    """Rename two entities of a running filter and exercise them afterwards.

    Returns how many times async_will_remove_from_hass ran during the renames.
    """
    hass.states.async_set(USAGE_SOURCE, STATE_OFF)
    entry = await add_filter(hass, "Furnace", USAGE_SOURCE)
    ids = entity_ids(hass, entry.entry_id)
    usage_old, button_old = ids["usage_time"], ids["reset_install_date"]
    days_id = ids["days_remaining"]

    await hass.services.async_call(
        DOMAIN, "set_usage_time", {"entry_id": entry.entry_id, "usage_hours": 12.5}, blocking=True
    )
    await hass.async_block_till_done()

    removals = 0
    original = base.BaseFilterEntity.async_will_remove_from_hass

    async def counting(self):
        nonlocal removals
        removals += 1
        await original(self)

    usage_new = "sensor.furnace_filter_runtime"
    button_new = "button.furnace_filter_changed"
    with patch.object(base.BaseFilterEntity, "async_will_remove_from_hass", counting):
        await rename(hass, usage_old, usage_new)
        await rename(hass, button_old, button_new)

    tag = "" if opted_in else " (control)"
    check(f"old usage entity ID is gone{tag}", hass.states.get(usage_old) is None)
    state = hass.states.get(usage_new)
    check(
        f"renamed usage sensor kept its hours{tag}",
        state is not None and float(state.state) == 12.5,
        f"state={state.state if state else None}",
    )
    live = live_entity(hass, usage_new)
    check(f"live entity carries the new ID{tag}", live is not None and live.entity_id == usage_new)

    # Listeners must have survived: the service reaches the entity through a
    # dispatcher signal, the button through its own entity ID.
    await hass.services.async_call(
        DOMAIN, "set_usage_time", {"entry_id": entry.entry_id, "adjust_hours": 1}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get(usage_new)
    check(
        f"usage updates still reach the renamed sensor{tag}",
        state is not None and float(state.state) == 13.5,
        f"state={state.state if state else None}",
    )

    before = hass.states.get(days_id)
    check(f"filter starts out overdue{tag}", before is not None and int(before.state) == 0)
    await hass.services.async_call("button", "press", {"entity_id": button_new}, blocking=True)
    await hass.async_block_till_done()
    days = hass.states.get(days_id)
    check(
        f"renamed button still resets the filter{tag}",
        days is not None and int(days.state) > 80,
        f"days remaining={days.state if days else None}",
    )
    usage = hass.states.get(usage_new)
    check(
        f"pressing the renamed button reset usage{tag}",
        usage is not None and float(usage.state) == 0,
        f"usage={usage.state if usage else None}",
    )

    ours = [r for r in errors.records if "filter_tracker" in r.name or "entity" in r.name]
    check(
        f"nothing logged at ERROR{tag}",
        not ours,
        "; ".join(f"{r.name}: {r.getMessage()}" for r in ours[:3]),
    )
    return removals


async def s2_rename_in_place():
    errors = ErrorLog()
    logging.getLogger().addHandler(errors)
    try:
        hass = await new_hass()
        check("integration set up", await async_setup_component(hass, DOMAIN, {}))
        removals = await _rename_scenario(hass, errors, opted_in=True)
        check("rename did not remove the entities", removals == 0, f"removals={removals}")
    finally:
        logging.getLogger().removeHandler(errors)


async def s3_control_without_opt_in():
    """The same scenario with the hook taken away must take the old path.

    Shows that s2's zero removals is down to the hook, not to the scenario.
    """
    errors = ErrorLog()
    logging.getLogger().addHandler(errors)
    hook = base.BaseFilterEntity.__dict__["async_entity_id_changed"]
    delattr(base.BaseFilterEntity, "async_entity_id_changed")
    entity._entity_class_requires_readd.cache_clear()
    try:
        hass = await new_hass()
        await async_setup_component(hass, DOMAIN, {})
        removals = await _rename_scenario(hass, errors, opted_in=False)
        check(
            "control: without the hook, each rename removes and re-adds",
            removals == 2,
            f"removals={removals}",
        )
    finally:
        base.BaseFilterEntity.async_entity_id_changed = hook
        entity._entity_class_requires_readd.cache_clear()
        logging.getLogger().removeHandler(errors)


SECTIONS = [
    ("1. every entity class opts in to in-place renames", s1_opt_in_covers_every_entity_class),
    ("2. renaming a running filter's entities", s2_rename_in_place),
    ("3. control: the same renames without the hook", s3_control_without_opt_in),
]


async def main() -> int:
    from homeassistant.const import __version__

    print(f"Home Assistant {__version__}, Python {sys.version.split()[0]}")
    for title, section in SECTIONS:
        print(f"\n== {title} ==")
        try:
            await section()
        except Exception:
            FAILED.append(f"{title} (crashed)")
            traceback.print_exc()
    for hass in HASSES:
        try:
            await hass.async_stop()
        except Exception:
            pass

    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}):")
        for label in FAILED:
            print(f"  - {label}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
