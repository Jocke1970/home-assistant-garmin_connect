"""Read-only Home Assistant service for Garmin Fitness probing."""

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

from .const import DOMAIN
from .fitness_probe import build_fitness_probe
from .services import _get_client

SERVICE_FITNESS_PROBE = "fitness_probe"

FITNESS_PROBE_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("days", default=90): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=365),
        ),
    }
)


async def async_setup_fitness_probe_service(hass: HomeAssistant) -> None:
    """Register the on-demand read-only Garmin Fitness probe."""
    if hass.services.has_service(DOMAIN, SERVICE_FITNESS_PROBE):
        return

    async def handle_fitness_probe(call: ServiceCall) -> ServiceResponse:
        """Fetch and return Garmin Fitness activity-load diagnostics."""
        client = _get_client(hass, entity_id=call.data.get("entity_id"))
        try:
            return await build_fitness_probe(
                client,
                days=call.data["days"],
                end_date=dt_util.now().date(),
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
    """Remove the Garmin Fitness probe service."""
    hass.services.async_remove(DOMAIN, SERVICE_FITNESS_PROBE)
