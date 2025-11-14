DOMAIN = "filter_tracker"

CONF_NAME = "name"
CONF_INSTALL_DATE = "install_date"
CONF_LIFESPAN_DAYS = "lifespan_days"
CONF_LIFESPAN_AMOUNT = "lifespan_amount"
CONF_LIFESPAN_UNIT = "lifespan_unit"
CONF_FILTER_TYPE = "filter_type"
CONF_FILTER_SIZE = "filter_size"
CONF_MANUFACTURER = "manufacturer"

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

SERVICE_SET_FILTER_REPLACED = "set_filter_replaced"
ATTR_ENTRY_ID = "entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_REPLACEMENT_DATETIME = "replacement_datetime"

DATA_ENTRIES = "entries"
SIGNAL_INSTALL_UPDATED = "filter_tracker_install_updated"
SIGNAL_CONFIG_UPDATED = "filter_tracker_config_updated"


def get_install_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_INSTALL_UPDATED}_{entry_id}"


def get_config_update_signal(entry_id: str) -> str:
    return f"{SIGNAL_CONFIG_UPDATED}_{entry_id}"
