"""Read-only Home Assistant services for Garmin Fitness diagnostics."""

from __future__ import annotations

import voluptuous as vol
from aiohttp import ClientError
from ha_garmin import GarminConnectError
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FITNESS_DATA_KEY
from .fitness_load_priority_backend import build_load_priority_report
from .fitness_probe import build_fitness_probe
from .services import _get_client

SERVICE_FITNESS_PROBE = "fitness_probe"
SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW = "fitness_load_priority_preview"

FITNESS_PROBE_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("days", default=90): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
        vol.Optional("max_hr"): vol.All(
            vol.Coerce(float), vol.Range(min=100, max=250)
        ),
        vol.Optional("sex"): vol.In(("male", "female")),
    }
)

_LOAD_METHODS = ("power", "hr", "pace", "garmin")
_SPORTS = ("walking", "cycling", "running", "rowing", "strength", "other")
FITNESS_LOAD_PRIORITY_PREVIEW_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("sport"): vol.In(_SPORTS),
        vol.Optional("priority"): vol.All(
            [vol.In(_LOAD_METHODS)], vol.Length(min=1, max=4)
        ),
        vol.Optional("override"): vol.In(_LOAD_METHODS),
        vol.Optional("ftp_watts"): vol.All(
            vol.Coerce(float), vol.Range(min=1, max=2500)
        ),
        vol.Optional("threshold_speed_mps"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=20)
        ),
        vol.Optional("limit", default=10): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=30)
        ),
    }
)


async def async_setup_fitness_probe_service(hass: HomeAssistant) -> None:
    """Register on-demand read-only Fitness diagnostics (never alter history)."""
    if hass.services.has_service(DOMAIN, SERVICE_FITNESS_PROBE):
        return

    async def handle_load_priority_preview(call: ServiceCall) -> ServiceResponse:
        """Select load sources from the already-cached account-specific context."""
        client = _get_client(hass, entity_id=call.data.get("entity_id"))
        fitness_coordinators = hass.data.get(FITNESS_DATA_KEY, {})
        fitness = next(
            (item for item in fitness_coordinators.values() if item.client is client),
            None,
        )
        if fitness is None or not fitness.configured or fitness.insight_context is None:
            raise HomeAssistantError(
                "Garmin Fitness history is not ready for this account; "
                "configure Fitness and wait for a successful refresh"
            )
        if fitness.user_max_hr is None or fitness.sex is None:
            raise HomeAssistantError("Garmin Fitness HR configuration is incomplete")

        try:
            return build_load_priority_report(
                fitness.insight_context,
                user_max_hr=fitness.user_max_hr,
                sex=fitness.sex,
                limit=call.data.get("limit", 10),
                sport=call.data.get("sport"),
                priority=call.data.get("priority"),
                override=call.data.get("override"),
                ftp_watts=call.data.get("ftp_watts"),
                threshold_speed_mps=call.data.get("threshold_speed_mps"),
            )
        except ValueError as err:
            raise HomeAssistantError(f"Invalid Load Priority preview: {err}") from err

    # Keep the original fitness_probe as the last registration to preserve
    # existing HA service integrations and probe runtime expectations.
    hass.services.async_register(
        DOMAIN,
        SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW,
        handle_load_priority_preview,
        schema=FITNESS_LOAD_PRIORITY_PREVIEW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def handle_fitness_probe(call: ServiceCall) -> ServiceResponse:
        """Fetch and return Garmin Fitness activity-load diagnostics."""
        client = _get_client(hass, entity_id=call.data.get("entity_id"))
        try:
            return await build_fitness_probe(
                client,
                days=call.data["days"],
                end_date=dt_util.now().date(),
                user_max_hr=call.data.get("max_hr"),
                sex=call.data.get("sex"),
            )
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise HomeAssistantError(f"Garmin Fitness probe failed: {err}") from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_FITNESS_PROBE,
        handle_fitness_probe,
        schema=FITNESS_PROBE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unload_fitness_probe_service(hass: HomeAssistant) -> None:
    """Remove both read-only Garmin Fitness actions."""
    if hass.services.has_service(DOMAIN, SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW):
        hass.services.async_remove(DOMAIN, SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW)
    hass.services.async_remove(DOMAIN, SERVICE_FITNESS_PROBE)
