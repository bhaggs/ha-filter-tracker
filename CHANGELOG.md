# Changelog

All notable changes to Filter Tracker are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-22

Filter Tracker has been useful for a while, but 0.5.0 had bugs that could
silently corrupt or lose a filter's install date and usage hours — the one thing
a tracker exists to get right. Those are fixed, and the integration now has a
test suite that pins the behaviour so they stay fixed. That is what 1.0 marks.

### ⚠️ Before you update

**Check your install dates.** Two separate bugs in 0.5.0 could replace a
filter's install date with a wrong but plausible-looking one:

- Reloading a filter erased its stored data. Home Assistant unloads a config
  entry on every *reload*, not just on deletion, and the integration deleted its
  stored install date and usage hours at that moment. The reload button, the
  `reload_config_entry` service, disabling an entry, and the integration's own
  options screen all triggered it. The date then silently reset to today.
- Install dates reverted to their original value. When a filter was created, the
  chosen date was parked in temporary storage and cleaned up by a background
  task that three parts of the integration raced. The cleanup frequently did not
  happen, and every later startup re-applied the *creation-time* date over
  whatever had since been set with the "Filter replaced" button. This is the
  cause behind reports of dates snapping back across every filter at once.

Both are fixed, and reads can no longer overwrite good data. Dates already
overwritten cannot be recovered automatically — correct them from the filter's
**Configure** screen.

**Thermostat usage hours will grow much more slowly.** See _Changed_ below.
Existing hours are kept as-is and are almost certainly overstated; reset them
with the "Filter replaced" button or `filter_tracker.set_usage_time`.

### Changed

- **Minimum Home Assistant version is now 2025.1.0.** 0.5.0 declared 2024.1.0,
  but its options screen already required 2024.11 or newer to work at all.
- **Thermostat runtime is measured from `hvac_action`, not `hvac_mode`.** A
  furnace left on "heat" all winter used to accrue 24 hours a day even though it
  ran for one or two. Thermostats that do not report `hvac_action` keep the old
  mode-based behaviour.
- **Time while Home Assistant is stopped is no longer counted.** Usage used to
  keep accruing across an outage, and kept climbing afterwards until the tracked
  entity next changed state, at which point the inflated total was saved
  permanently. Startup now reconciles against the entity's real state.
- **Clearing a filter's usage sensor keeps its accumulated hours** instead of
  discarding them, and re-adding one restores them. Reset deliberately with the
  button or `set_usage_time`.
- Config changes now reload the filter rather than pushing updates through a
  custom notification path.

### Added

- **Editable install date.** The Configure screen has a date picker, pre-filled
  with the filter's current date, for correcting a date or recovering from an
  accidental "Filter replaced" press. Saving the form without touching the date
  leaves it exactly as it was. ([#4](https://github.com/bhaggs/ha-filter-tracker/issues/4))
- **Long-term statistics** for usage hours, filter life remaining, and days
  remaining, so they can be graphed across a filter's whole life rather than the
  few days normal history keeps. Statistics start from when you update; earlier
  history is not backfilled.

### Fixed

- Install dates resetting to today, or reverting to their creation-time value.
  ([#5](https://github.com/bhaggs/ha-filter-tracker/issues/5))
- A failed or corrupt storage read being persisted over good data as today's
  date, unattended, by a background calendar refresh.
- Adding or removing a usage sensor did nothing until Home Assistant was
  restarted — the Usage Time entity would not appear or disappear.
- The shared Filter Tracker calendar could vanish. It was owned by whichever
  filter loaded first; reloading that filter left the calendar permanently
  unavailable, and deleting it removed the calendar entirely even with other
  filters still set up.
- Changing a filter's tracked entity caused all of its entities to start
  tracking and writing the same usage file at once, each with its own running
  total.
- `filter_tracker.set_filter_replaced` and `filter_tracker.set_usage_time` were
  unregistered when the last filter was removed, silently breaking any
  automation that called them.

### Removed

- The **Filter type** sensor no longer carries `install_date` and
  `replacement_due_date` attributes. Both have always had their own sensors —
  `Filter last replaced` and `Filter replacement due date` — so use those in
  templates. Carrying duplicates wrote two extra copies of the same dates into
  the recorder database on every update.

### Performance

- Entities are no longer polled every 30 seconds to recalculate values that only
  change at midnight. They refresh when the date changes, and the usage sensor
  ticks once a minute only while its tracked entity is actually running.
- Usage data is written in batches rather than once per on/off flip. A rapidly
  cycling fan used to cause a disk write every time it switched. Pending data is
  always flushed before Home Assistant shuts down or a filter reloads.

### Internal

- Added a test suite — 64 tests covering the bugs above, plus upgrade tests that
  verify data written by 0.5.0 still loads and that every entity keeps its
  existing ID. CI runs pytest, hassfest and HACS validation.
- Documentation consolidated into a single README. The repository previously
  carried two separately maintained copies that had drifted 143 lines apart, and
  the one HACS renders was the less complete of the two.

### Pre-releases

1.0.0 was tested as `0.6.0-beta.1` (2026-08-25), `0.6.0-beta.2` (2026-09-10) and
`0.6.0-beta.3` (2026-09-11). All of their changes are included above.

## [0.5.0-beta] - 2025-12-06

Initial public beta.

[1.0.0]: https://github.com/bhaggs/ha-filter-tracker/compare/v0.5.0-beta...v1.0.0
[0.5.0-beta]: https://github.com/bhaggs/ha-filter-tracker/releases/tag/v0.5.0-beta
