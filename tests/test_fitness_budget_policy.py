"""Tests for priority-aware Garmin Fitness planning budget semantics."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from ha_garmin.fitness.models import ActivityMetrics, DailyLoad
from ha_garmin.fitness.pipeline import build_training_history_from_daily_loads
from ha_garmin.fitness.trimp import compute_trimp

from custom_components.garmin_connect.fitness_budget_policy import (
    build_priority_aware_daily_budget,
)


def _activity(
    *,
    activity_id: int,
    day: date,
    activity_type: str,
    avg_hr: float,
    max_hr: float,
    minutes: float,
    normalized_power: float | None = None,
    aerobic_te: float | None = 1.5,
    anaerobic_te: float | None = 0.0,
) -> ActivityMetrics:
    return ActivityMetrics(
        activity_id=activity_id,
        calendar_date=day,
        start_time=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        activity_type=activity_type,
        duration_minutes=minutes,
        distance_meters=3000.0,
        avg_hr=avg_hr,
        max_hr=max_hr,
        calories=None,
        aerobic_training_effect=aerobic_te,
        anaerobic_training_effect=anaerobic_te,
        garmin_training_load=14.4,
        vo2max=None,
        avg_power=normalized_power,
        normalized_power=normalized_power,
    )


def _context(activity: ActivityMetrics, today_load: float) -> SimpleNamespace:
    start = activity.calendar_date - timedelta(days=59)
    loads: list[DailyLoad] = []
    current = start
    while current <= activity.calendar_date:
        is_today = current == activity.calendar_date
        load = today_load if is_today else 20.0
        loads.append(
            DailyLoad(
                date=current,
                activity_count=1 if is_today else 0,
                loaded_activity_count=1 if is_today else 0,
                known_load=load,
                load=load,
                complete=True,
            )
        )
        current += timedelta(days=1)
    history = build_training_history_from_daily_loads("trimp", loads)
    return SimpleNamespace(
        history=history,
        activities=(activity,),
        resting_hr_by_date={activity.calendar_date: 60.0},
    )


def test_easy_walk_does_not_consume_training_budget() -> None:
    today = date(2026, 9, 16)
    walk = _activity(
        activity_id=1,
        day=today,
        activity_type="walking",
        avg_hr=90.0,
        max_hr=105.0,
        minutes=25.0,
    )
    trimp = compute_trimp(walk, 60.0, 180.0, "male")
    assert trimp is not None

    result = build_priority_aware_daily_budget(
        _context(walk, trimp),
        250.0,
        user_max_hr=180.0,
        sex="male",
    )

    assert result["planning_policy_version"] == 2
    assert result["canonical_current_load"] == pytest.approx(trimp, abs=0.001)
    assert result["excluded_low_intensity_load"] == pytest.approx(trimp, abs=0.001)
    assert result["budget_consuming_load"] == 0.0
    assert result["current_load"] == 0.0
    assert result["low_intensity_activity_count"] == 1
    assert result["training_activity_count"] == 0
    decision = result["activity_decisions"][0]
    assert decision["selected_source"] == "hr"
    assert decision["intensity_lane"] == "low"


def test_hard_cycling_uses_power_and_consumes_budget_when_ftp_exists() -> None:
    today = date(2026, 9, 16)
    ride = _activity(
        activity_id=2,
        day=today,
        activity_type="cycling",
        avg_hr=155.0,
        max_hr=175.0,
        minutes=60.0,
        normalized_power=240.0,
        aerobic_te=4.0,
    )
    trimp = compute_trimp(ride, 60.0, 180.0, "male")
    assert trimp is not None

    result = build_priority_aware_daily_budget(
        _context(ride, trimp),
        250.0,
        user_max_hr=180.0,
        sex="male",
        ftp_watts=250.0,
    )

    assert result["excluded_low_intensity_load"] == 0.0
    assert result["budget_consuming_load"] == pytest.approx(trimp, abs=0.001)
    assert result["training_activity_count"] == 1
    decision = result["activity_decisions"][0]
    assert decision["selected_source"] == "power"
    assert decision["intensity_lane"] == "training"
    assert decision["intensity_basis"] == "power_if"
    assert decision["intensity_value"] == pytest.approx(0.96, abs=0.001)
