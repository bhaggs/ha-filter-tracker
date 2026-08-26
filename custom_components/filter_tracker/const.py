DOMAIN = "filter_tracker"

CONF_NAME = "name"
CONF_INSTALL_DATE = "install_date"
CONF_LIFESPAN_DAYS = "lifespan_days"
CONF_LIFESPAN_AMOUNT = "lifespan_amount"
CONF_LIFESPAN_UNIT = "lifespan_unit"
CONF_FILTER_TYPE = "filter_type"
CONF_FILTER_SIZE = "filter_size"
CONF_MANUFACTURER = "manufacturer"
CONF_USAGE_SENSOR = "usage_sensor"

# Legacy key: the config flow parked the chosen install date in a temp store
# keyed by flow_id, because entry_id did not exist yet. Setup migrates and
# removes it; it should never persist past the first setup of an entry.
CONF_TEMP_STORAGE_KEY = "_temp_storage_key"

# Lifespan unit conversion factors
# Note: These are approximate conversions for simplicity:
# - "months" uses 30 days (actual months range from 28-31 days)
# - "years" uses 365 days (doesn't account for leap years)
# This means some minor drift may occur over long periods
# (e.g., ~1 day per year for years, variable for months)
LIFESPAN_UNIT_FACTORS = {
    "days": 1,
    "weeks": 7,
    "months": 30,
    "years": 365,
}

PLATFORMS = ["sensor", "binary_sensor", "button", "calendar"]

# Climate hvac_action values that mean the system is genuinely running.
# Preferred over the mode below whenever the entity reports it: a thermostat
# left on "heat" all winter sits in "idle" most of the time, and counting the
# mode would accrue 24/7 for what is usually the main furnace-filter use case.
ATTR_HVAC_ACTION = "hvac_action"
CLIMATE_ACTIVE_ACTIONS = [
    "heating",
    "cooling",
    "drying",
    "fan",
    "preheating",
    "defrosting",
]

# Fallback for climate entities that do not report hvac_action: the mode alone.
# Also the rule used to derive the active flag for usage stores written before
# it was persisted.
CLIMATE_ACTIVE_STATES = ["heat", "cool", "heat_cool", "dry", "fan_only", "auto"]

SERVICE_SET_FILTER_REPLACED = "set_filter_replaced"
SERVICE_SET_USAGE_TIME = "set_usage_time"
ATTR_ENTRY_ID = "entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_REPLACEMENT_DATETIME = "replacement_datetime"
ATTR_USAGE_HOURS = "usage_hours"
ATTR_ADJUST_HOURS = "adjust_hours"

DATA_ENTRIES = "entries"
# One calendar serves the whole integration, but HA entities must belong to a
# config entry, so one entry owns it. Tracking which lets the calendar be
# recreated when that entry reloads, and re-homed when it is deleted.
DATA_CALENDAR_OWNER = "calendar_owner_entry_id"
SIGNAL_INSTALL_UPDATED = "filter_tracker_install_updated"
SIGNAL_CONFIG_UPDATED = "filter_tracker_config_updated"
SIGNAL_USAGE_UPDATED = "filter_tracker_usage_updated"


def get_install_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_INSTALL_UPDATED}_{entry_id}"


def get_config_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_CONFIG_UPDATED}_{entry_id}"


def get_usage_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_USAGE_UPDATED}_{entry_id}"
