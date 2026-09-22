# Filter Tracker for Home Assistant

A Home Assistant custom integration for tracking household filters that need regular replacement, such as air filters, water filters, furnace filters, and more.

## Features

- **Track Multiple Filters**: Add unlimited filters with different replacement schedules
- **Flexible Scheduling**: Set lifespan in days, weeks, months, or years
- **Runtime Tracking** (optional): Accumulate real usage hours from a fan, switch, or thermostat, so a filter is replaced on how hard it worked rather than the calendar alone
- **Comprehensive Entity Support**:
  - 5 sensors per filter (last replaced, due date, days remaining, life remaining, filter type)
  - A 6th usage-time sensor when runtime tracking is enabled
  - Binary sensor for expired status
  - Button to mark filter as replaced
  - Unified calendar showing all filter due dates
- **Long-Term Statistics**: Usage hours and remaining life are recorded as statistics, so they can be graphed across a filter's whole life
- **Rich Metadata**: Track filter type, physical size, and manufacturer
- **Editable Install Date**: Correct a date from the options screen, or set it with the button or a service
- **Automation Ready**: Use sensors, binary sensors, calendar, and services to create reminders and automations

## Requirements

Home Assistant **2025.1.0** or later.

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add the repository URL: `https://github.com/bhaggs/ha-filter-tracker`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Filter Tracker" and install
8. Restart Home Assistant

### Manual Installation

1. Copy the `filter_tracker` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

### Adding a Filter

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Filter Tracker"
4. Fill in the form:
   - **Filter Name**: Descriptive name (e.g., "Living Room Air Purifier")
   - **Install Date**: When the filter was installed or replaced
   - **Lifespan Amount**: How long the filter lasts
   - **Lifespan Unit**: Days, weeks, months, or years
   - **Filter Type**: Type of filter (e.g., "HEPA", "MERV11", "Carbon")
   - **Filter Size** (optional): Physical dimensions (e.g., "16x25x1", "20x20x1")
   - **Manufacturer** (optional): Filter manufacturer
   - **Usage Sensor** (optional): An entity whose runtime should be tracked — see [Runtime Tracking](#runtime-tracking)

### Editing a Filter

1. Go to Settings → Devices & Services
2. Find the Filter Tracker integration
3. Click on a specific filter entry
4. Click "Configure"
5. Update any settings (install date, name, lifespan, filter type, filter size, manufacturer, usage sensor)
   - The install date picker is pre-filled with the current value. Leave it alone unless you are correcting it — saving the form with the date unchanged will not alter it.
   - You can also update the install date with the "Filter replaced" button or the `filter_tracker.set_filter_replaced` service.

Saving the form reloads the filter, so its entities are rebuilt with the new configuration. Adding or removing a usage sensor creates or removes the usage-time entity immediately.

### Deleting a Filter

1. Go to Settings → Devices & Services
2. Find the Filter Tracker integration
3. Click on a specific filter entry
4. Click the three dots and select "Delete"

## Entities

For each filter, the following entities are created:

### Sensors

1. **Filter Last Replaced** (`sensor.<name>_filter_last_replaced`)
   - Type: Timestamp sensor
   - Shows when the filter was last installed/replaced
   - Device class: `timestamp`

2. **Filter Replacement Due Date** (`sensor.<name>_filter_replacement_due_date`)
   - Type: Timestamp sensor
   - Shows the date when filter replacement is due
   - Device class: `timestamp`

3. **Filter Life Days Remaining** (`sensor.<name>_filter_life_days_remaining`)
   - Type: Sensor (days)
   - Shows how many days remain until replacement is due
   - Returns 0 if filter is overdue

4. **Filter Life Remaining** (`sensor.<name>_filter_life_remaining`)
   - Type: Sensor (%)
   - Shows percentage of filter life remaining (0-100%)
   - Useful for visual indicators and progress bars

5. **Filter Type** (`sensor.<name>_filter_type`)
   - Type: Diagnostic sensor
   - State shows the filter type
   - Attributes:
     - `rated_lifespan_days`: Total filter lifespan
     - `filter_size`: Physical dimensions (if specified)
     - `manufacturer`: Manufacturer name
     - `usage_sensor`, `usage_sensor_available`: present only when runtime tracking is configured

6. **Usage Time** (`sensor.<name>_usage_time`) — **only when a usage sensor is configured**
   - Type: Duration sensor (hours)
   - Device class: `duration`
   - Shows accumulated runtime in hours (rounded to 2 decimal places)
   - Includes time since the tracked entity started running, so it advances while in use
   - Attributes:
     - `usage_sensor`: Entity ID being tracked
     - `usage_sensor_state`: Raw state of the tracked entity (`on`, `off`, `heat`, …)
     - `usage_sensor_active`: Whether that state currently counts as *running*. For a thermostat this comes from `hvac_action`, so it can legitimately disagree with the state above — mode `heat` with action `idle` is not running.
     - `usage_sensor_available`: Whether the tracked entity is currently available
     - `usage_sensor_last_changed`: When the tracked entity last changed running state
     - `accumulated_seconds`: Total accumulated usage in seconds

### Binary Sensor

**Filter Expired** (`binary_sensor.<name>_filter_expired`)
- Device class: `problem`
- "On" when the filter is past its due date

### Button

**Filter Replaced** (`button.<name>_filter_replaced`)
- Press to mark the filter as replaced
- Sets the install date to now, and resets accumulated usage hours to zero

### Calendar

**Filter Tracker** (`calendar.filter_tracker`)
- A single calendar entity showing all filter replacement due dates
- Events display as "[Filter Name] - Replacement Due"

## Runtime Tracking

Setting a **Usage Sensor** on a filter adds a Usage Time sensor that accumulates
how long the tracked entity has actually been running.

Supported entity types and what counts as running:

| Entity type | Counts as running when |
|---|---|
| `binary_sensor`, `switch`, `input_boolean`, `fan` | state is `on` |
| `climate` reporting `hvac_action` | action is `heating`, `cooling`, `drying`, `fan`, `preheating`, or `defrosting` |
| `climate` without `hvac_action` | mode is `heat`, `cool`, `heat_cool`, `dry`, `fan_only`, or `auto` |

For thermostats, `hvac_action` is strongly preferred and used automatically when
available. A thermostat left on `heat` all winter sits `idle` most of the time,
so counting the *mode* would accrue 24 hours a day for a furnace that ran for
one.

Notes:

- Accumulation pauses while the tracked entity is `unavailable` or `unknown`
- Time is **not** counted while Home Assistant is not running: on startup the
  integration reconciles against the entity's real state, because there is no
  way to know what it did while nothing was watching
- Usage data persists across restarts, and is saved in batches rather than on
  every state change
- Changing the tracked entity, or clearing it entirely, **preserves** the
  accumulated hours. Use the "Filter replaced" button or `set_usage_time` to
  reset them deliberately.

## Long-Term Statistics

Usage time, filter life remaining, and days remaining are recorded as long-term
statistics, so they can be graphed over months rather than only the few days
normal history retains.

Usage time is recorded as a total that resets when the filter is replaced, so
each filter's run appears as its own cycle.

Statistics accumulate from the moment the integration records them — history
from before is not backfilled.

## Services

### `filter_tracker.set_filter_replaced`

Manually set when a filter was replaced.

**Parameters:**
- `entry_id` (optional): The config entry ID of the filter
- `device_id` (optional): The device ID of the filter
- `replacement_datetime` (optional): When the filter was replaced (defaults to now)

Provide either `entry_id` or `device_id`, not both.

```yaml
# Replace filter now using device_id
action: filter_tracker.set_filter_replaced
data:
  device_id: "xyz789uvw012"

# Replace filter with a specific date/time
action: filter_tracker.set_filter_replaced
data:
  device_id: "xyz789uvw012"
  replacement_datetime: "2026-01-15 14:30:00"
```

### `filter_tracker.set_usage_time`

Set or adjust accumulated usage time. Requires a filter with a usage sensor
configured; calendar-only filters raise an error.

**Parameters:**
- `entry_id` / `device_id`: Which filter to target — provide exactly one
- `usage_hours`: Set usage time to this absolute value in hours
- `adjust_hours`: Add (positive) or subtract (negative) hours

Provide exactly one of `usage_hours` or `adjust_hours`. A negative result is
clamped to zero.

```yaml
# Set usage to exactly 150 hours
action: filter_tracker.set_usage_time
data:
  device_id: "xyz789"
  usage_hours: 150

# Subtract 5 hours from current usage
action: filter_tracker.set_usage_time
data:
  entry_id: "abc123"
  adjust_hours: -5
```

## Automation Examples

### Send Notification When Filter Expires

```yaml
automation:
  - alias: "Notify when living room filter expires"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_air_filter_filter_expired
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Filter Replacement Due"
          message: "The living room air filter needs to be replaced!"
```

### Warning When Filter is Almost Due

```yaml
automation:
  - alias: "Warn when furnace filter is almost due"
    trigger:
      - platform: numeric_state
        entity_id: sensor.furnace_filter_filter_life_days_remaining
        below: 7
    action:
      - service: notify.mobile_app
        data:
          title: "Filter Replacement Soon"
          message: "Furnace filter needs replacement in {{ states('sensor.furnace_filter_filter_life_days_remaining') }} days"
```

### Notify After a Number of Runtime Hours

```yaml
automation:
  - alias: "Furnace filter has run 300 hours"
    trigger:
      - platform: numeric_state
        entity_id: sensor.furnace_filter_usage_time
        above: 300
    action:
      - service: notify.mobile_app
        data:
          title: "Filter Replacement Due"
          message: "The furnace filter has run for 300 hours."
```

### Create a Filter Maintenance Dashboard

```yaml
type: entities
title: Filter Maintenance
entities:
  - entity: sensor.furnace_filter_filter_life_remaining
    name: Furnace Filter
  - entity: sensor.air_purifier_filter_filter_life_remaining
    name: Air Purifier
  - entity: sensor.water_filter_filter_life_remaining
    name: Water Filter
```

### Use Calendar for Filter Reminders

```yaml
type: calendar
entities:
  - calendar.filter_tracker
```

## Using Attributes in Templates

```yaml
# Filter size and rated lifespan
{{ state_attr('sensor.furnace_filter_filter_type', 'filter_size') }}
{{ state_attr('sensor.furnace_filter_filter_type', 'rated_lifespan_days') }}

# Is the tracked entity actually running right now?
{{ state_attr('sensor.furnace_filter_usage_time', 'usage_sensor_active') }}

# Precise accumulated usage, in seconds
{{ state_attr('sensor.furnace_filter_usage_time', 'accumulated_seconds') }}
```

For the install and due dates, use the dedicated sensors rather than attributes:

```yaml
{{ states('sensor.furnace_filter_filter_last_replaced') }}
{{ states('sensor.furnace_filter_filter_replacement_due_date') }}
```

## Notes on Date Calculations

The integration uses approximate conversions for simplicity:
- **Months** = 30 days (actual months range from 28-31 days)
- **Years** = 365 days (doesn't account for leap years)

This may cause minor drift over long periods (approximately 1 day per year for yearly filters). For most household filters, this level of precision is sufficient.

## Troubleshooting

### Wrong install date

Open the filter's **Configure** screen and correct the install date, or use the
`filter_tracker.set_filter_replaced` service. The "Filter replaced" button sets
it to right now.

### Usage time not accumulating

1. Check the `usage_sensor_active` attribute on the Usage Time sensor — this is
   the value that actually drives accumulation
2. For a thermostat, `usage_sensor_active` follows `hvac_action`. If the mode is
   `heat` but the system is idle, nothing accrues — this is intended
3. Check `usage_sensor_available` is `true`
4. Verify the tracked entity's domain is supported (binary_sensor, switch,
   input_boolean, fan, climate)

### Usage hours look too high after upgrading from 0.5.x

Earlier versions counted a thermostat as running whenever its *mode* was active,
and also counted time while Home Assistant was stopped. Both are fixed, but
hours already accumulated are not recalculated. Reset them with the "Filter
replaced" button or set a specific value with `filter_tracker.set_usage_time`.

### Statistics graphs are empty

Long-term statistics start from when the integration began recording them and
are not backfilled. Give it a day.

## Support

- **Issues**: [GitHub Issues](https://github.com/bhaggs/ha-filter-tracker/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/bhaggs/ha-filter-tracker/discussions)

## License

This integration is released under the MIT License.

## Credits

Developed by @bhaggs
