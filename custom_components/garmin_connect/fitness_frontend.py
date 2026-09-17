"""Serve the HACS-packaged Garmin Fitness cards without editing /config/www."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

FRONTEND_URL = "/garmin_connect/frontend"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_register_fitness_frontend(hass: HomeAssistant) -> None:
    """Expose the packaged JavaScript from the integration's own directory."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(FRONTEND_DIR), False)]
    )
