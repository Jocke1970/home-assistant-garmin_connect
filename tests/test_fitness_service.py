"""Tests for the Garmin Fitness probe service."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import SupportsResponse

from custom_components.garmin_connect.const import DOMAIN
from custom_components.garmin_connect.fitness_service import (
    SERVICE_FITNESS_PROBE,
    async_setup_fitness_probe_service,
    async_unload_fitness_probe_service,
)


def _mock_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.has_service.return_value = False

    client = AsyncMock()
    coordinators = MagicMock()
    coordinators.core.client = client

    entry = MagicMock()
    entry.entry_id = "entry_1"
    entry.runtime_data = coordinators
    hass.config_entries.async_entries.return_value = [entry]
    return hass


def _handler(hass: MagicMock):
    for call in hass.services.async_register.call_args_list:
        if call.args[0] == DOMAIN and call.args[1] == SERVICE_FITNESS_PROBE:
            return call.args[2]
    raise AssertionError("fitness_probe service was not registered")


async def test_fitness_probe_service_uses_existing_client_and_returns_response() -> None:
    hass = _mock_hass()
    expected = {"probe_version": 3, "activities": {"total": 1}}

    with (
        patch(
            "custom_components.garmin_connect.fitness_service.build_fitness_probe",
            new_callable=AsyncMock,
            return_value=expected,
        ) as probe,
        patch("custom_components.garmin_connect.fitness_service.dt_util.now") as now,
    ):
        now.return_value = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)
        await async_setup_fitness_probe_service(hass)

        call = MagicMock()
        call.data = {"days": 90, "max_hr": 175.0, "sex": "male"}
        result = await _handler(hass)(call)

    client = hass.config_entries.async_entries.return_value[0].runtime_data.core.client
    probe.assert_awaited_once_with(
        client,
        days=90,
        end_date=datetime(2026, 9, 3).date(),
        user_max_hr=175.0,
        sex="male",
    )
    assert result == expected

    register_call = hass.services.async_register.call_args
    assert register_call.args[:2] == (DOMAIN, SERVICE_FITNESS_PROBE)
    assert register_call.kwargs["supports_response"] is SupportsResponse.ONLY


async def test_fitness_probe_service_allows_coverage_only() -> None:
    hass = _mock_hass()

    with patch(
        "custom_components.garmin_connect.fitness_service.build_fitness_probe",
        new_callable=AsyncMock,
        return_value={"probe_version": 3},
    ) as probe:
        await async_setup_fitness_probe_service(hass)
        call = MagicMock()
        call.data = {"days": 30}
        await _handler(hass)(call)

    probe.assert_awaited_once()
    assert probe.await_args.kwargs["user_max_hr"] is None
    assert probe.await_args.kwargs["sex"] is None


def test_fitness_probe_action_exposes_trimp_parameters() -> None:
    services_yaml = (
        Path(__file__).parents[1]
        / "custom_components"
        / "garmin_connect"
        / "services.yaml"
    ).read_text(encoding="utf-8")
    fitness_probe = services_yaml.split("\nfitness_probe:\n", maxsplit=1)[1]

    assert "\n    max_hr:\n" in fitness_probe
    assert "\n    sex:\n" in fitness_probe
    assert "Maximum heart rate used for Banister TRIMP comparison." in fitness_probe
    assert "Sex-specific Banister TRIMP coefficient" in fitness_probe


async def test_fitness_probe_service_registers_only_once() -> None:
    hass = _mock_hass()
    hass.services.has_service.return_value = True

    await async_setup_fitness_probe_service(hass)

    hass.services.async_register.assert_not_called()


async def test_unload_fitness_probe_service() -> None:
    hass = _mock_hass()

    await async_unload_fitness_probe_service(hass)

    hass.services.async_remove.assert_called_once_with(DOMAIN, SERVICE_FITNESS_PROBE)
