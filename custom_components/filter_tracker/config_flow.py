import voluptuous as vol
from datetime import datetime
import logging

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.selector import selector
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_INSTALL_DATE,
    CONF_LIFESPAN_DAYS,
    CONF_LIFESPAN_AMOUNT,
    CONF_LIFESPAN_UNIT,
    CONF_FILTER_TYPE,
    CONF_FILTER_SIZE,
    CONF_MANUFACTURER,
    CONF_USAGE_SENSOR,
    CONF_TEMP_STORAGE_KEY,
    LIFESPAN_UNIT_FACTORS,
    get_config_update_signal,
)
from .tracker_data import async_save_install_datetime

_LOGGER = logging.getLogger(__name__)


def _build_unit_options() -> list[dict[str, str]]:
    """Build dropdown options for lifespan unit selector."""
    return [
        {"label": unit.capitalize(), "value": unit}
        for unit in LIFESPAN_UNIT_FACTORS.keys()
    ]


def _decompose_lifespan_days(lifespan_days: int) -> tuple[int, str]:
    """
    Convert stored lifespan_days back to amount and unit.

    Returns:
        Tuple of (amount, unit) that when multiplied give lifespan_days.
        Prefers larger units when possible (years > months > weeks > days).
    """
    for unit, factor in [("years", 365), ("months", 30), ("weeks", 7)]:
        if lifespan_days % factor == 0:
            return lifespan_days // factor, unit
    return lifespan_days, "days"


def _build_schema(
    include_install_date: bool = False,
    existing_data: dict | None = None,
) -> vol.Schema:
    """
    Build config schema for setup or options flow.

    Args:
        include_install_date: Whether to include install_date field (setup only)
        existing_data: The existing config entry data (for options flow)

    Returns:
        Schema for the config flow form
    """
    unit_options = _build_unit_options()
    use_existing_data = existing_data is not None

    # Determine defaults based on flow type
    if use_existing_data:
        name_default = existing_data.get(CONF_NAME, "")
        filter_type_default = existing_data.get(CONF_FILTER_TYPE, "")
        filter_size_default = existing_data.get(CONF_FILTER_SIZE, "")
        manufacturer_default = existing_data.get(CONF_MANUFACTURER, "")
        usage_sensor_default = existing_data.get(CONF_USAGE_SENSOR, "")

        # Reverse-engineer lifespan amount/unit from stored days
        lifespan_days = existing_data.get(CONF_LIFESPAN_DAYS, 90)
        lifespan_amount, lifespan_unit = _decompose_lifespan_days(lifespan_days)
    else:
        # Hardcoded defaults for initial setup
        name_default = None
        filter_type_default = None
        filter_size_default = None
        manufacturer_default = None
        usage_sensor_default = None
        lifespan_amount = 3
        lifespan_unit = "months"

    schema_dict = {}

    # Add shared fields with appropriate Required/Optional wrapper
    if use_existing_data:
        # Options flow - all fields are optional
        schema_dict[vol.Required(CONF_NAME, default=name_default)] = str
        schema_dict[vol.Required(CONF_LIFESPAN_AMOUNT, default=lifespan_amount)] = vol.All(
            vol.Coerce(int), vol.Range(min=1)
        )
        schema_dict[vol.Required(CONF_LIFESPAN_UNIT, default=lifespan_unit)] = selector({
            "select": {"options": unit_options, "mode": "dropdown"}
        })
        schema_dict[vol.Required(CONF_FILTER_TYPE, default=filter_type_default)] = str
        schema_dict[vol.Optional(CONF_FILTER_SIZE, default=filter_size_default)] = str
        schema_dict[vol.Optional(CONF_MANUFACTURER, default=manufacturer_default)] = str
        schema_dict[vol.Optional(CONF_USAGE_SENSOR, description={"suggested_value": usage_sensor_default})] = selector({
            "entity": {"domain": ["binary_sensor", "input_boolean", "switch", "fan", "climate"]}
        })
    else:
        # Initial setup - name and lifespan are required
        schema_dict[vol.Required(CONF_NAME)] = str

        # Add install_date after name
        if include_install_date:
            default_dt = dt_util.now().date().isoformat()
            schema_dict[vol.Required(CONF_INSTALL_DATE, default=default_dt)] = selector(
                {"date": {}}
            )

        schema_dict[vol.Required(CONF_LIFESPAN_AMOUNT, default=lifespan_amount)] = vol.All(
            vol.Coerce(int), vol.Range(min=1)
        )
        schema_dict[vol.Required(CONF_LIFESPAN_UNIT, default=lifespan_unit)] = selector({
            "select": {"options": unit_options, "mode": "dropdown"}
        })
        schema_dict[vol.Required(CONF_FILTER_TYPE)] = str
        schema_dict[vol.Optional(CONF_FILTER_SIZE)] = str
        schema_dict[vol.Optional(CONF_MANUFACTURER)] = str
        schema_dict[vol.Optional(CONF_USAGE_SENSOR)] = selector({
            "entity": {"domain": ["binary_sensor", "input_boolean", "switch", "fan", "climate"]}
        })

    return vol.Schema(schema_dict)


class FilterTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return FilterTrackerOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        schema = _build_schema(include_install_date=True)

        if user_input is not None:
            install_date = datetime.strptime(user_input[CONF_INSTALL_DATE], "%Y-%m-%d").date()
            install_dt = dt_util.start_of_local_day(install_date)

            # Remove from data before saving
            user_input.pop(CONF_INSTALL_DATE)
            lifespan_amount = user_input.pop(CONF_LIFESPAN_AMOUNT)
            lifespan_unit = user_input.pop(CONF_LIFESPAN_UNIT)
            user_input[CONF_LIFESPAN_DAYS] = lifespan_amount * LIFESPAN_UNIT_FACTORS[lifespan_unit]

            # Store install datetime in a temporary location using flow_id
            # The sensor platform will migrate this to the actual entry_id
            temp_storage_key = f"_flow_{self.flow_id}"
            try:
                await async_save_install_datetime(self.hass, temp_storage_key, install_dt)
            except Exception as err:
                _LOGGER.error("Failed to save install datetime during setup: %s", err)
                errors["base"] = "storage_error"
                return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

            # Store the temp key so sensor platform knows to migrate it
            user_input[CONF_TEMP_STORAGE_KEY] = temp_storage_key

            # Create entry (without install_date)
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        # Default show form when first loaded or errors present
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class FilterTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Filter Tracker."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # Calculate new lifespan in days
            lifespan_amount = user_input.get(CONF_LIFESPAN_AMOUNT)
            lifespan_unit = user_input.get(CONF_LIFESPAN_UNIT)

            if lifespan_amount and lifespan_unit:
                user_input[CONF_LIFESPAN_DAYS] = lifespan_amount * LIFESPAN_UNIT_FACTORS[lifespan_unit]
                # Remove the amount and unit from options since we store days
                user_input.pop(CONF_LIFESPAN_AMOUNT, None)
                user_input.pop(CONF_LIFESPAN_UNIT, None)
            
            # Normalize empty string to None for usage_sensor (entity selector sends "" when cleared)
            if CONF_USAGE_SENSOR not in user_input:
                user_input[CONF_USAGE_SENSOR] = None

            # Merge new values with existing data
            updated_data = {**self.config_entry.data}

            # Update each field if provided (allow empty strings to clear optional fields)
            for key in [CONF_NAME, CONF_LIFESPAN_DAYS, CONF_FILTER_TYPE, CONF_FILTER_SIZE, CONF_MANUFACTURER, CONF_USAGE_SENSOR]:
                if key in user_input:
                    updated_data[key] = user_input[key]

            # Update title if name changed
            new_title = updated_data.get(CONF_NAME, self.config_entry.title)

            _LOGGER.debug(
                "Updating entry %s: title='%s', data=%s",
                self.config_entry.entry_id,
                new_title,
                updated_data
            )

            # Update the config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=new_title,
                data=updated_data
            )

            # Check if usage sensor was added or removed (requires reload to create/remove entity)
            old_usage_sensor = self.config_entry.data.get(CONF_USAGE_SENSOR)
            new_usage_sensor = updated_data.get(CONF_USAGE_SENSOR)

            # Detect if usage sensor was added or removed (not just changed)
            usage_sensor_added = not old_usage_sensor and new_usage_sensor
            usage_sensor_removed = old_usage_sensor and not new_usage_sensor

            if usage_sensor_added or usage_sensor_removed:
                _LOGGER.info(
                    "Usage sensor %s for filter %s, reloading config entry to %s usage hours entity",
                    "added" if usage_sensor_added else "removed",
                    updated_data.get(CONF_NAME),
                    "create" if usage_sensor_added else "remove"
                )
                # Schedule reload after options flow completes
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )
                # Return early - reload will handle state updates
                return self.async_create_entry(title="", data={})

            # Schedule signal dispatch to happen AFTER options flow completes
            # This ensures the event loop can process scheduled state updates
            signal = get_config_update_signal(self.config_entry.entry_id)

            async def _send_signal():
                async_dispatcher_send(self.hass, signal, updated_data)

            self.hass.async_create_task(_send_signal())

            return self.async_create_entry(title="", data={})

        # Build schema using existing config data
        options_schema = _build_schema(existing_data=self.config_entry.data)

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors
        )
