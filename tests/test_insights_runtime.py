"""Tests for Home Assistant Garmin Insights V1 orchestration."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from ha_garmin.fitness import (
    ActivityMetrics,
    AcwrPoint,
    LoadSeriesAssessment,
    RampRatePoint,
    TrainingHistoryResult,
    TrainingLoadPoint,
)
from ha_garmin.history import TrimpTrainingContext
from ha_garmin.insights import DailyRecoveryMetrics

from custom_components.garmin_connect.insights_coordinator import InsightsCoordinator
from custom_components.garmin_connect.insights_sensor import GarminInsightsOverviewSensor

_DAY = date(2026, 9, 7)


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry_1"
    return entry


def _activity() -> ActivityMetrics:
    return ActivityMetrics(
        activity_id=123,
        calendar_date=_DAY,
        start_time=datetime(2026, 9, 7, 12, tzinfo=UTC),
        activity_type="cycling",
        duration_minutes=60.0,
        distance_meters=20000.0,
        avg_hr=135.0,
        max_hr=165.0,
        calories=500.0,
        aerobic_training_effect=2.0,
        anaerobic_training_effect=0.2,
        garmin_training_load=80.0,
        vo2max=44.0,
        avg_power=150.0,
        normalized_power=165.0,
    )


def _context() -> TrimpTrainingContext:
    assessment = LoadSeriesAssessment(
        total_days=90,
        activity_days=10,
        rest_days=80,
        complete_days=90,
        incomplete_days=(),
        ready=True,
    )
    history = TrainingHistoryResult(
        source="trimp",
        algorithm_version=4,
        assessment=assessment,
        daily_loads=(),
        training_points=(
            TrainingLoadPoint(
                date=_DAY,
                daily_load=40.0,
                ctl=40.0,
                atl=40.0,
                tsb=0.0,
            ),
        ),
        acwr_points=(
            AcwrPoint(
                date=_DAY,
                acute_average=40.0,
                chronic_average=40.0,
                acwr=1.0,
            ),
        ),
        ramp_rate_points=(
            RampRatePoint(
                date=_DAY,
                ctl=40.0,
                ctl_7d_ago=39.0,
                ramp_rate=1.0,
            ),
        ),
    )
    return TrimpTrainingContext(
        activities=(_activity(),),
        resting_hr_by_date={_DAY: 50.0},
        history=history,
    )


def _recovery() -> DailyRecoveryMetrics:
    return DailyRecoveryMetrics(
        date=_DAY,
        resting_hr=50.0,
        resting_hr_7d_avg=50.0,
        hrv_status="BALANCED",
        hrv_weekly_avg=47.0,
        hrv_last_night_avg=48.0,
        hrv_baseline_balanced_low=42.0,
        hrv_baseline_balanced_upper=55.0,
        sleep_score=85.0,
        body_battery_most_recent=72.0,
        average_stress_level=22.0,
        training_readiness=80.0,
        recovery_minutes=300.0,
        summary_available=True,
        sleep_available=True,
        hrv_available=True,
        readiness_available=True,
    )


def _fitness(*, context: TrimpTrainingContext | None = None) -> MagicMock:
    fitness = MagicMock()
    fitness.configured = True
    fitness.last_update_success = True
    fitness.insight_context = context
    fitness.insight_personal_trimp_max = 120.0 if context is not None else None
    return fitness


async def test_insights_coordinator_builds_and_evaluates_current_snapshot() -> None:
    coordinator = InsightsCoordinator(
        MagicMock(),
        _entry(),
        AsyncMock(),
        _fitness(context=_context()),
    )
    coordinator.history_client.fetch_daily_recovery_metrics = AsyncMock(
        return_value=_recovery()
    )

    with patch(
        "custom_components.garmin_connect.insights_coordinator.dt_util.now",
        return_value=datetime(2026, 9, 7, 8, tzinfo=UTC),
    ):
        data = await coordinator._async_update_data()

    coordinator.history_client.fetch_daily_recovery_metrics.assert_awaited_once_with(_DAY)
    assert data["configured"] is True
    assert data["status"] == "positive"
    assert data["snapshot_complete"] is True
    assert data["snapshot_date"] == "2026-09-07"
    assert data["result_ids"] == ["favourable_training_signal"]
    assert data["primary_result_id"] == "favourable_training_signal"
    assert data["primary_severity"] == "positive"
    assert data["training"]["algorithm_version"] == 4
    assert data["training"]["acwr"] == 1.0
    assert data["recovery"]["training_readiness"] == 80.0
    assert data["recent_activity_count"] == 1
    assert data["recent_activities"][0]["activity_type"] == "cycling"


async def test_insights_waits_for_canonical_fitness_context() -> None:
    coordinator = InsightsCoordinator(
        MagicMock(),
        _entry(),
        AsyncMock(),
        _fitness(context=None),
    )
    coordinator.history_client.fetch_daily_recovery_metrics = AsyncMock()

    data = await coordinator._async_update_data()

    coordinator.history_client.fetch_daily_recovery_metrics.assert_not_awaited()
    assert data["configured"] is True
    assert data["status"] == "waiting_for_fitness"
    assert data["snapshot_complete"] is False
    assert data["result_count"] == 0


def test_insights_overview_sensor_exposes_status_and_rule_provenance() -> None:
    coordinator = MagicMock()
    coordinator.data = {
        "configured": True,
        "status": "caution",
        "snapshot_complete": True,
        "as_of": "2026-09-07T08:00:00+00:00",
        "snapshot_date": "2026-09-07",
        "ruleset_version": 1,
        "result_count": 1,
        "result_ids": ["recovery_caution"],
        "primary_result_id": "recovery_caution",
        "primary_severity": "caution",
        "primary_confidence": "medium",
        "results": [{"id": "recovery_caution", "severity": "caution"}],
        "data_quality": {"complete": True},
        "recovery": {"training_readiness": 35.0},
        "training": {"acwr": 1.0},
        "load_focus": {"complete": True},
        "recent_activity_count": 0,
        "recent_activities": [],
    }

    sensor = GarminInsightsOverviewSensor(coordinator, "entry_1")

    assert sensor.native_value == "caution"
    attrs = sensor.extra_state_attributes
    assert attrs["primary_result_id"] == "recovery_caution"
    assert attrs["ruleset_version"] == 1
    assert attrs["results"] == [
        {"id": "recovery_caution", "severity": "caution"}
    ]
