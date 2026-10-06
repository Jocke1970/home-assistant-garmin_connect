"""HACS frontend packaging and route tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from custom_components.garmin_connect import async_setup
from custom_components.garmin_connect.fitness_frontend import FRONTEND_DIR, FRONTEND_URL


def test_hacs_frontend_assets_match_source() -> None:
    """The HACS installation must ship exactly the reviewed JS files."""
    source_dir = Path(__file__).resolve().parents[1] / "www" / "garmin_fitness_card"
    for name in ("garmin-fitness-card.js", "garmin-fitness-dashboard-card.js"):
        assert (FRONTEND_DIR / name).is_file()
        assert (FRONTEND_DIR / name).read_bytes() == (source_dir / name).read_bytes()


async def test_async_setup_registers_packaged_static_route() -> None:
    """Expose the cards without touching local files or Lovelace resources."""
    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    assert await async_setup(hass, {}) is True

    hass.http.async_register_static_paths.assert_awaited_once()
    configs = hass.http.async_register_static_paths.call_args.args[0]
    assert len(configs) == 1
    assert configs[0].url_path == FRONTEND_URL
    assert configs[0].path == str(FRONTEND_DIR)
    assert configs[0].cache_headers is False
