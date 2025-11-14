# Filter Tracker for Home Assistant

A Home Assistant custom integration for tracking household filters that need regular replacement, such as air filters, water filters, furnace filters, and more.

## Features

- **Track Multiple Filters**: Add unlimited filters with different replacement schedules
- **Flexible Scheduling**: Set lifespan in days, weeks, months, or years
- **Comprehensive Entity Support**:
  - 5 sensors per filter (install date, due date, days remaining, percentage remaining, filter type)
  - Binary sensor for expired status
  - Button to mark filter as replaced
  - Unified calendar showing all filter due dates
- **Rich Metadata**: Track filter type, physical size, and manufacturer
- **Easy Reset**: Button entity and service to mark filter as replaced with custom date/time support
- **Calendar Integration**: View all filter replacement due dates in Home Assistant's calendar view
- **Automation Ready**: Use sensors, binary sensors, calendar, and services to create reminders and automations

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

### Editing a Filter

1. Go to Settings → Devices & Services
2. Find the Filter Tracker integration
3. Click on a specific filter entry
4. Click "Configure"
5. Update any settings (name, lifespan, filter type, filter size, manufacturer)
   - Note: Install date cannot be changed via options flow - use the service or button instead

### Deleting a Filter

1. Go to Settings → Devices & Services
2. Find the Filter Tracker integration
3. Click on a specific filter entry
4. Click the three dots and select "Delete"

## Usage

For each filter, the following entities are created:

#### Sensors

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
   - Contains rich state attributes with all filter metadata:
     - `rated_lifespan_days`: Total filter lifespan
     - `install_date`: When filter was installed (ISO format)
     - `replacement_due_date`: When replacement is due (ISO format)
     - `filter_size`: Physical dimensions (if specified)
     - `manufacturer`: Manufacturer name

#### Binary Sensor

**Filter Expired** (`binary_sensor.<name>_filter_expired`)
- Type: Binary sensor (problem)
- Device class: `problem`
- "On" when the filter is past its due date
- Perfect for automations and notifications

#### Button

**Filter Replaced** (`button.<name>_filter_replaced`)
- Press to mark the filter as replaced
- Updates the install date to the current date/time
- All sensors automatically recalculate

#### Calendar

**Filter Tracker** (`calendar.filter_tracker`)
- Single calendar entity showing all filter replacement due dates
- Events display as "[Filter Name] - Replacement Due"
- Event descriptions include filter type and size
- Integrates with Home Assistant's calendar view

### Service

#### `filter_tracker.set_filter_replaced`

Manually set when a filter was replaced.

**Parameters:**
- `entry_id` (optional): The config entry ID of the filter
- `device_id` (optional): The device ID of the filter
- `replacement_datetime` (optional): When the filter was replaced (defaults to now)

**Note**: You must provide either `entry_id` OR `device_id`, but not both.

**Example Service Calls:**

```yaml
# Replace filter now using entry_id
service: filter_tracker.set_filter_replaced
data:
  entry_id: "abc123def456"

# Replace filter now using device_id
service: filter_tracker.set_filter_replaced
data:
  device_id: "xyz789uvw012"

# Replace filter with specific date/time
service: filter_tracker.set_filter_replaced
data:
  device_id: "xyz789uvw012"
  replacement_datetime: "2025-01-15 14:30:00"
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
  - entity: sensor.fridge_filter_filter_life_remaining
    name: Refrigerator Filter
```

### Use Calendar for Filter Reminders

The Filter Tracker calendar shows all upcoming filter replacements:

```yaml
# View calendar in a dashboard card
type: calendar
entities:
  - calendar.filter_tracker
```

## Filter Metadata

The **Filter Type** diagnostic sensor includes comprehensive state attributes:

- `rated_lifespan_days`: Total lifespan of the filter in days
- `install_date`: When the filter was installed (ISO format timestamp)
- `replacement_due_date`: When filter replacement is due (ISO format timestamp)
- `filter_size`: Physical dimensions of the filter (e.g., "16x25x1")
- `manufacturer`: Manufacturer name

To access these attributes in templates or automations:

```yaml
# Example: Get the filter size
{{ state_attr('sensor.furnace_filter_filter_type', 'filter_size') }}

# Example: Get the rated lifespan
{{ state_attr('sensor.furnace_filter_filter_type', 'rated_lifespan_days') }}
```

## Notes on Date Calculations

The integration uses approximate conversions for simplicity:
- **Months** = 30 days (actual months range from 28-31 days)
- **Years** = 365 days (doesn't account for leap years)

This may cause minor drift over long periods (approximately 1 day per year for yearly filters). For most household filters, this level of precision is sufficient.

## Troubleshooting

### Wrong install date

Use the `filter_tracker.set_filter_replaced` service to correct the install date, or press the "Reset Filter" button to set the install date to current day.

### Can't edit filter after creation

Ensure you're on Home Assistant 2024.1.0 or later, then:
1. Go to Settings → Devices & Services
2. Click on the filter entry
3. Click "Configure"

Note there can be a delay between updating the configuration details and the device entities reflecting that update.

## Support

- **Issues**: [GitHub Issues](https://github.com/bhaggs/ha-filter-tracker/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/bhaggs/ha-filter-tracker/discussions)

## License

This integration is released under the MIT License.

## Credits

Developed by @bhaggs
