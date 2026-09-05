"""Tests for the permanent Garmin Fitness runtime layer."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


def _training_points(days: int = 180) -> list[dict]:
    start = date(2026, 9, 4) - timedelta(days=days - 1)
    points = []
    for offset in range(days):
        point_date = start + timedelta(days=offset)
        points.append(
            {
                "date": point_date.isoformat(),
                "daily_load": 0.0,
                "ctl": round(20.0 - (offset * 0.05), 3),
                "atl": round(10.0 - (offset * 0.02), 3),
                "tsb": round(10.0 - (offset * 0.03), 3),
            }
        )
    points[-1] = {
        "date": "2026-09-04",
        "daily_load": 7.5,
        "ctl": 11.2,
        "atl": 2.1,
        "tsb": 9.1,
    }
    return points


def _load_focus_points(days: int = 180) -> list[dict]:
    start = date(2026, 9, 4) - timedelta(days=days - 1)
    points = []
    for offset in range(days):
        point_date = start + timedelta(days=offset)
        points.append(
            {
                "date": point_date.isoformat(),
                "complete": True,
                "activity_count": 0,
                "covered_activities": 0,
                "missing_activities": 0,
                "low_aerobic": 0.0,
                "high_aerobic": 0.0,
                "anaerobic": 0.0,
            }
        )
    points[-1].update(
        {
            "activity_count": 1,
            "covered_activities": 1,
            "low_aerobic": 2.2,
            "high_aerobic": 0.0,
            "anaerobic": 0.3,
        }
    )
    return points


@pytest.fixture(autouse=True)
def mock_strain_calibration():
    calibration = {
        "personal_trimp_max": 120.0,
        "personal_trimp_max_source": "calibrated",
        "strain_calibration_sessions": 40,
        "strain_calibration_min_sessions": 30,
        "strain_calibration_multiplier": 1.2,
        "strain_calibration_complete": True,
    }
    with patch(
        "custom_components.garmin_connect.fitness_coordinator.async_fetch_strain_calibration",
        new_callable=AsyncMock,
        return_value=calibration,
    ) as mocked:
        yield mocked


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
    assert data["acwr"] is None
    assert data["ramp_rate"] is None
    assert data["strain"] is None
    assert data["history_days"] == 90
    assert data["calculation_days"] == 180
    assert data["warmup_days"] == 90
    assert data["warmup_recovered"] is False
    assert data["acwr_acute_days"] == 7
    assert data["acwr_chronic_days"] == 28
    assert data["ramp_period_days"] == 7
    assert data["strain_scale_max"] == 21.0
    assert data["hard_day_threshold"] == 14.0


async def test_fitness_coordinator_uses_warmup_and_exposes_last_90_days() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    points = _training_points()
    probe_result = {
        "algorithm_version": 1,
        "window": {
            "days": 180,
            "start_date": "2026-03-09",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": True,
                "blocker_dates": [],
                "points": points,
                "latest": points[-1],
            }
        },
        "load_focus": {"points": _load_focus_points()},
    }

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
        return_value=probe_result,
    ) as probe:
        data = await coordinator._async_update_data()

    probe.assert_awaited_once()
    assert probe.await_args.kwargs["days"] == 180
    assert probe.await_args.kwargs["user_max_hr"] == 175.0
    assert probe.await_args.kwargs["sex"] == "male"
    assert data["configured"] is True
    assert data["ready"] is True
    assert data["history_complete"] is True
    assert data["daily_load"] == 7.5
    assert data["ctl"] == 11.2
    assert data["atl"] == 2.1
    assert data["tsb"] == 9.1
    assert data["acwr"] == 4.0
    assert data["ramp_rate"] == -0.2
    assert data["strain"] == 1.27
    assert data["load_focus_low_aerobic"] == 2.2
    assert data["load_focus_high_aerobic"] == 0.0
    assert data["load_focus_anaerobic"] == 0.3
    assert data["load_focus_history_complete"] is True
    assert data["load_focus_activity_coverage_percent"] == 100.0
    assert data["load_focus_total_activities"] == 1
    assert data["load_focus_covered_activities"] == 1
    assert data["load_focus_incomplete_dates"] == []
    assert data["load_source"] == "trimp"
    assert data["algorithm_version"] == 1
    assert data["history_days"] == 90
    assert len(data["history"]) == 90
    assert data["history_start"] == "2026-06-07"
    assert data["history_end"] == "2026-09-04"
    assert data["history"][0]["acwr"] is None
    assert data["history"][0]["ramp_rate"] == -0.35
    assert data["history"][0]["strain"] == 0.0
    assert data["history"][-1]["acwr"] == 4.0
    assert data["history"][-1]["ramp_rate"] == -0.2
    assert data["history"][-1]["strain"] == 1.27
    assert data["calculation_days"] == 180
    assert data["calculation_start"] == "2026-03-09"
    assert data["calculation_end"] == "2026-09-04"
    assert data["warmup_days"] == 90
    assert data["effective_calculation_days"] == 180
    assert data["effective_calculation_start"] == "2026-03-09"
    assert data["effective_warmup_days"] == 90
    assert data["warmup_recovered"] is False
    assert data["warmup_blocker_dates"] == []
    assert data["acwr_acute_days"] == 7
    assert data["acwr_chronic_days"] == 28
    assert data["ramp_period_days"] == 7
    assert data["strain_scale_max"] == 21.0
    assert data["hard_day_threshold"] == 14.0
    assert data["personal_trimp_max"] == 120.0
    assert data["personal_trimp_max_source"] == "calibrated"
    assert data["strain_calibration_sessions"] == 40
    assert data["strain_calibration_min_sessions"] == 30
    assert data["strain_calibration_complete"] is True


async def test_fitness_coordinator_recovers_from_old_warmup_blocker() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    recovery_points = _training_points(days=173)
    blocked_probe = {
        "algorithm_version": 1,
        "window": {
            "days": 180,
            "start_date": "2026-03-09",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": False,
                "blocker_dates": ["2026-03-15"],
                "points": None,
                "latest": None,
            }
        },
    }
    recovery_probe = {
        "algorithm_version": 1,
        "window": {
            "days": 173,
            "start_date": "2026-03-16",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": True,
                "blocker_dates": [],
                "points": recovery_points,
                "latest": recovery_points[-1],
            }
        },
    }

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
        side_effect=[blocked_probe, recovery_probe],
    ) as probe:
        data = await coordinator._async_update_data()

    assert probe.await_count == 2
    assert probe.await_args_list[0].kwargs["days"] == 180
    assert probe.await_args_list[1].kwargs["days"] == 173
    assert probe.await_args_list[1].kwargs["end_date"] == date(2026, 9, 4)
    assert data["ready"] is True
    assert data["history_complete"] is True
    assert len(data["history"]) == 90
    assert data["history_start"] == "2026-06-07"
    assert data["history_end"] == "2026-09-04"
    assert data["acwr"] == 4.0
    assert data["ramp_rate"] == -0.55
    assert data["strain"] == 1.27
    assert data["blocker_dates"] == []
    assert data["warmup_blocker_dates"] == ["2026-03-15"]
    assert data["warmup_recovered"] is True
    assert data["effective_calculation_days"] == 173
    assert data["effective_calculation_start"] == "2026-03-16"
    assert data["effective_warmup_days"] == 83


async def test_fitness_coordinator_does_not_recover_recent_warmup_blocker() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    blocked_probe = {
        "algorithm_version": 1,
        "window": {
            "days": 180,
            "start_date": "2026-03-09",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": False,
                "blocker_dates": ["2026-05-15"],
                "points": None,
                "latest": None,
            }
        },
    }

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
        return_value=blocked_probe,
    ) as probe:
        data = await coordinator._async_update_data()

    probe.assert_awaited_once()
    assert data["ready"] is False
    assert data["history_complete"] is False
    assert data["history"] == []
    assert data["acwr"] is None
    assert data["ramp_rate"] is None
    assert data["strain"] is None
    assert data["blocker_dates"] == ["2026-05-15"]
    assert data["warmup_blocker_dates"] == ["2026-05-15"]
    assert data["warmup_recovered"] is False


async def test_fitness_coordinator_refuses_short_calculation_series() -> None:
    coordinator = _coordinator(
        {CONF_FITNESS_MAX_HR: 175, CONF_FITNESS_SEX: "male"}
    )
    points = _training_points(days=89)
    probe_result = {
        "algorithm_version": 1,
        "window": {
            "days": 180,
            "start_date": "2026-03-09",
            "end_date": "2026-09-04",
        },
        "training_series": {
            "trimp": {
                "ready": True,
                "blocker_dates": [],
                "points": points,
                "latest": points[-1],
            }
        },
    }

    with patch(
        "custom_components.garmin_connect.fitness_coordinator.build_fitness_probe",
        new_callable=AsyncMock,
        return_value=probe_result,
    ):
        data = await coordinator._async_update_data()

    assert data["ready"] is False
    assert data["history_complete"] is False
    assert data["history"] == []
    assert data["ctl"] is None
    assert data["acwr"] is None
    assert data["ramp_rate"] is None
    assert data["strain"] is None


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
        "acwr": 0.82,
        "ramp_rate": -1.25,
        "strain": 1.08,
        "load_focus_low_aerobic": 2.4,
        "load_focus_high_aerobic": 0.0,
        "load_focus_anaerobic": 0.5,
        "history": [{"date": "2026-09-03", "daily_load": 6.708}],
        "history_days": 90,
        "history_start": "2026-06-06",
        "history_end": "2026-09-03",
        "history_complete": True,
        "calculation_days": 180,
        "calculation_start": "2026-03-08",
        "calculation_end": "2026-09-03",
        "warmup_days": 90,
        "effective_calculation_days": 173,
        "effective_calculation_start": "2026-03-15",
        "effective_warmup_days": 83,
        "warmup_recovered": True,
        "warmup_blocker_dates": ["2026-03-14"],
        "blocker_dates": [],
        "acwr_acute_days": 7,
        "acwr_chronic_days": 28,
        "ramp_period_days": 7,
        "strain_scale_max": 21.0,
        "hard_day_threshold": 14.0,
        "load_focus_algorithm_version": 1,
        "load_focus_source": "garmin_training_effect",
        "load_focus_high_aerobic_threshold": 3.0,
        "load_focus_history_complete": True,
        "load_focus_activity_coverage_percent": 100.0,
        "load_focus_total_activities": 12,
        "load_focus_covered_activities": 12,
        "load_focus_incomplete_dates": [],
        "personal_trimp_max": 120.0,
        "personal_trimp_max_source": "calibrated",
        "strain_calibration_sessions": 40,
        "strain_calibration_min_sessions": 30,
        "strain_calibration_multiplier": 1.2,
        "strain_calibration_complete": True,
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
    assert sensor.extra_state_attributes["calculation_days"] == 180
    assert sensor.extra_state_attributes["warmup_days"] == 90
    assert sensor.extra_state_attributes["effective_calculation_days"] == 173
    assert sensor.extra_state_attributes["effective_warmup_days"] == 83
    assert sensor.extra_state_attributes["warmup_recovered"] is True
    assert sensor.extra_state_attributes["warmup_blocker_dates"] == ["2026-03-14"]
    assert sensor.extra_state_attributes["acwr_acute_days"] == 7
    assert sensor.extra_state_attributes["acwr_chronic_days"] == 28
    assert sensor.extra_state_attributes["ramp_period_days"] == 7
    assert sensor.extra_state_attributes["strain_scale_max"] == 21.0
    assert sensor.extra_state_attributes["hard_day_threshold"] == 14.0
    assert sensor.extra_state_attributes["load_focus_algorithm_version"] == 1
    assert sensor.extra_state_attributes["load_focus_source"] == "garmin_training_effect"
    assert sensor.extra_state_attributes["load_focus_high_aerobic_threshold"] == 3.0
    assert sensor.extra_state_attributes["load_focus_history_complete"] is True
    assert sensor.extra_state_attributes["load_focus_activity_coverage_percent"] == 100.0
    assert sensor.extra_state_attributes["personal_trimp_max"] == 120.0
    assert sensor.extra_state_attributes["personal_trimp_max_source"] == "calibrated"
    assert sensor.extra_state_attributes["strain_calibration_sessions"] == 40
    assert "history" not in sensor.extra_state_attributes

    acwr_sensor = GarminFitnessSensor(
        coordinator,
        next(item for item in FITNESS_SENSOR_DESCRIPTIONS if item.key == "acwr"),
        "entry_1",
    )
    ramp_sensor = GarminFitnessSensor(
        coordinator,
        next(item for item in FITNESS_SENSOR_DESCRIPTIONS if item.key == "ramp_rate"),
        "entry_1",
    )
    strain_sensor = GarminFitnessSensor(
        coordinator,
        next(item for item in FITNESS_SENSOR_DESCRIPTIONS if item.key == "strain"),
        "entry_1",
    )
    low_focus_sensor = GarminFitnessSensor(
        coordinator,
        next(
            item
            for item in FITNESS_SENSOR_DESCRIPTIONS
            if item.key == "load_focus_low_aerobic"
        ),
        "entry_1",
    )
    assert acwr_sensor.native_value == 0.82
    assert acwr_sensor.native_unit_of_measurement is None
    assert ramp_sensor.native_value == -1.25
    assert ramp_sensor.native_unit_of_measurement == "TRIMP"
    assert strain_sensor.native_value == 1.08
    assert strain_sensor.native_unit_of_measurement is None
    assert low_focus_sensor.native_value == 2.4
    assert low_focus_sensor.native_unit_of_measurement == "TE"


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
    assert len(entities) == 10
    assert {entity.unique_id for entity in entities} == {
        "entry_1_fitness_daily_load",
        "entry_1_fitness_ctl",
        "entry_1_fitness_atl",
        "entry_1_fitness_tsb",
        "entry_1_fitness_acwr",
        "entry_1_fitness_ramp_rate",
        "entry_1_fitness_strain",
        "entry_1_fitness_load_focus_low_aerobic",
        "entry_1_fitness_load_focus_high_aerobic",
        "entry_1_fitness_load_focus_anaerobic",
    }
