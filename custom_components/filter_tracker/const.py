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

# Climate states that count as "active" for usage tracking
# These states indicate the HVAC system is actively running
CLIMATE_ACTIVE_STATES = ["heat", "cool", "heat_cool", "dry", "fan_only", "auto"]

SERVICE_SET_FILTER_REPLACED = "set_filter_replaced"
SERVICE_SET_USAGE_TIME = "set_usage_time"
ATTR_ENTRY_ID = "entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_REPLACEMENT_DATETIME = "replacement_datetime"
ATTR_USAGE_HOURS = "usage_hours"
ATTR_ADJUST_HOURS = "adjust_hours"

DATA_ENTRIES = "entries"
SIGNAL_INSTALL_UPDATED = "filter_tracker_install_updated"
SIGNAL_CONFIG_UPDATED = "filter_tracker_config_updated"
SIGNAL_USAGE_UPDATED = "filter_tracker_usage_updated"


def get_install_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_INSTALL_UPDATED}_{entry_id}"


def get_config_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_CONFIG_UPDATED}_{entry_id}"


def get_usage_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_USAGE_UPDATED}_{entry_id}"
