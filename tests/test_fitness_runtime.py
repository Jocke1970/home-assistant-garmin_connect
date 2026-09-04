"""Tests for the permanent Garmin Fitness runtime layer."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import Platform

from custom_components.garmin_connect.const import (
    CONF_FITNESS_MAX_HR,
    CONF_FITNESS_SEX,
)
from custom_components.garmin_connect.fitness_coordinator import FitnessCoordinator
from custom_components.garmin_connect.fitness_sensor import (
    FITNESS_SENSOR_DESCRIPTIONS,
    GarminFitnessSensor,
    async_add_fitness_sensor_entities,
)


def _entry(options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry_1"
    entry.options = options or {}
    return entry


def _coordinator(options: dict | None = None) -> FitnessCoordinator:
    return FitnessCoordinator(MagicMock(), _entry(options), AsyncMock())


async def test_fitness_coordinator_does_not_call_garmin_until_configured() -> None:
    coordinator = _coordinator()

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
    ) as probe:
        data = await coordinator._async_update_data()

    probe.assert_not_awaited()
    assert data["configured"] is False
    assert data["ready"] is False
    assert data["load_source"] == "trimp"
    assert data["daily_load"] is None


async def test_fitness_coordinator_exposes_latest_canonical_values() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    probe_result = {
        "algorithm_version": 1,
        "window": {
            "days": 90,
            "start_date": "2026-06-07",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": True,
                "blocker_dates": [],
                "points": [
                    {
                        "date": "2026-09-04",
                        "daily_load": 7.5,
                        "ctl": 11.2,
                        "atl": 2.1,
                        "tsb": 9.1,
                    }
                ],
                "latest": {
                    "date": "2026-09-04",
                    "daily_load": 7.5,
                    "ctl": 11.2,
                    "atl": 2.1,
                    "tsb": 9.1,
                },
            }
        },
    }

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
        return_value=probe_result,
    ) as probe:
        data = await coordinator._async_update_data()

    probe.assert_awaited_once()
    assert probe.await_args.kwargs["days"] == 90
    assert probe.await_args.kwargs["user_max_hr"] == 175.0
    assert probe.await_args.kwargs["sex"] == "male"
    assert data["configured"] is True
    assert data["ready"] is True
    assert data["history_complete"] is True
    assert data["daily_load"] == 7.5
    assert data["ctl"] == 11.2
    assert data["atl"] == 2.1
    assert data["tsb"] == 9.1
    assert data["load_source"] == "trimp"
    assert data["algorithm_version"] == 1


def test_fitness_sensor_exposes_value_and_provenance_without_history_attribute() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    coordinator.data = {
        "configured": True,
        "ready": True,
        "daily_load": 6.708,
        "ctl": 11.045,
        "atl": 1.764,
        "tsb": 9.281,
        "history": [{"date": "2026-09-03", "daily_load": 6.708}],
        "history_days": 90,
        "history_start": "2026-06-06",
        "history_end": "2026-09-03",
        "history_complete": True,
        "blocker_dates": [],
        "load_source": "trimp",
        "algorithm_version": 1,
        "max_hr": 175,
        "sex": "male",
    }

    sensor = GarminFitnessSensor(
        coordinator,
        FITNESS_SENSOR_DESCRIPTIONS[0],
        "entry_1",
    )

    assert sensor.native_value == 6.708
    assert sensor.unique_id == "entry_1_fitness_daily_load"
    assert sensor.extra_state_attributes["load_source"] == "trimp"
    assert sensor.extra_state_attributes["history_complete"] is True
    assert "history" not in sensor.extra_state_attributes


async def test_add_fitness_entities_uses_loaded_garmin_sensor_platform() -> None:
    hass = MagicMock()
    entry = _entry()
    coordinator = _coordinator()
    platform = MagicMock()
    platform.domain = Platform.SENSOR
    platform.config_entry = entry
    platform.async_add_entities = AsyncMock()

    with patch(
        "custom_components.garmin_connect.fitness_sensor.async_get_platforms",
        return_value=[platform],
    ):
        await async_add_fitness_sensor_entities(hass, entry, coordinator)

    platform.async_add_entities.assert_awaited_once()
    entities = list(platform.async_add_entities.await_args.args[0])
    assert len(entities) == 4
    assert {entity.unique_id for entity in entities} == {
        "entry_1_fitness_daily_load",
        "entry_1_fitness_ctl",
        "entry_1_fitness_atl",
        "entry_1_fitness_tsb",
    }
