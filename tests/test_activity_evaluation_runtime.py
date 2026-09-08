"""Tests for Home Assistant recent activity evaluation runtime."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ha_garmin.fitness import ActivityMetrics

from custom_components.garmin_connect.activity_evaluation_coordinator import (
    ActivityEvaluationCoordinator,
)
from custom_components.garmin_connect.activity_evaluation_presentation import (
    activity_option_label,
    present_activity_evaluation,
)
from custom_components.garmin_connect.activity_evaluation_sensor import (
    GarminActivityEvaluationSensor,
)

_DAY = date(2026, 9, 8)


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry_1"
    return entry


def _activity(
    activity_id: int,
    *,
    activity_type: str = "virtual_ride",
    start_hour: int = 18,
    duration_minutes: float = 30.0,
    aerobic_te: float = 4.0,
    anaerobic_te: float = 0.5,
    max_hr: float = 185.0,
) -> ActivityMetrics:
    return ActivityMetrics(
        activity_id=activity_id,
        calendar_date=_DAY,
        start_time=datetime(2026, 9, 8, start_hour, tzinfo=UTC),
        activity_type=activity_type,
        duration_minutes=duration_minutes,
        distance_meters=15000.0,
        avg_hr=150.0,
        max_hr=max_hr,
        calories=400.0,
        aerobic_training_effect=aerobic_te,
        anaerobic_training_effect=anaerobic_te,
        garmin_training_load=80.0,
        vo2max=None,
        avg_power=220.0 if activity_type == "virtual_ride" else None,
        normalized_power=235.0 if activity_type == "virtual_ride" else None,
    )


def _detail_payload(power: float = 260.0) -> dict:
    return {
        "metricDescriptors": [
            {"key": "directTimestamp", "metricsIndex": 0},
            {"key": "directPower", "metricsIndex": 1},
            {"key": "directHeartRate", "metricsIndex": 2},
        ],
        "activityDetailMetrics": [
            {"metrics": [1_757_353_200_000 + second * 1000, power, 175.0]}
            for second in range(1501)
        ],
    }


def _fitness(activities: tuple[ActivityMetrics, ...]) -> MagicMock:
    fitness = MagicMock()
    fitness.configured = True
    fitness.last_update_success = True
    fitness.user_max_hr = 195.0
    fitness.insight_context = SimpleNamespace(activities=activities)
    fitness.data = {
        "history": [
            {
                "date": _DAY.isoformat(),
                "acwr": 0.57,
                "strain": 5.1,
                "tsb": 5.7,
            }
        ]
    }
    return fitness


async def test_activity_evaluation_builds_selected_pass_and_post_context() -> None:
    client = MagicMock()
    client.get_activity_details = AsyncMock(return_value=_detail_payload())
    fitness = _fitness((_activity(123),))
    body = MagicMock()
    body.data = {"weightKg": 70.0}

    coordinator = ActivityEvaluationCoordinator(
        MagicMock(),
        _entry(),
        client,
        fitness,
        body,
    )
    data = await coordinator._async_update_data()

    assert data["ready"] is True
    assert data["evaluation_count"] == 1
    assert data["selected_activity_id"] == 123
    selected = data["selected_evaluation"]
    assert selected["assessment_id"] == "aerobic_development"
    assert selected["best_5m_power"] == 260.0
    assert selected["best_20m_power"] == 260.0
    assert selected["estimated_vo2max"] == 47.1
    assert selected["estimated_ftp_watts"] == 247
    assert selected["post_acwr"] == 0.57
    assert selected["post_strain"] == 5.1
    assert selected["post_tsb"] == 5.7
    assert selected["post_context_scope"] == "day"
    client.get_activity_details.assert_awaited_once_with(
        123,
        max_chart_size=5000,
        max_poly_size=1,
    )


async def test_activity_evaluation_keeps_only_five_newest_activities() -> None:
    activities = tuple(
        _activity(
            activity_id=100 + index,
            activity_type="rowing_v2",
            start_hour=12 + index,
        )
        for index in range(6)
    )
    client = MagicMock()
    client.get_activity_details = AsyncMock()
    body = MagicMock()
    body.data = {"weightKg": 70.0}

    coordinator = ActivityEvaluationCoordinator(
        MagicMock(),
        _entry(),
        client,
        _fitness(activities),
        body,
    )
    data = await coordinator._async_update_data()

    assert [item["activity_id"] for item in data["evaluations"]] == [105, 104, 103, 102, 101]
    assert data["selected_activity_id"] == 105
    client.get_activity_details.assert_not_awaited()


async def test_activity_detail_samples_are_cached_between_refreshes() -> None:
    client = MagicMock()
    client.get_activity_details = AsyncMock(return_value=_detail_payload())
    body = MagicMock()
    body.data = {"weightKg": 70.0}
    coordinator = ActivityEvaluationCoordinator(
        MagicMock(),
        _entry(),
        client,
        _fitness((_activity(123),)),
        body,
    )

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert client.get_activity_details.await_count == 1


async def test_activity_detail_failure_falls_back_to_summary_only() -> None:
    client = MagicMock()
    client.get_activity_details = AsyncMock(side_effect=RuntimeError("not ready"))
    body = MagicMock()
    body.data = {"weightKg": 70.0}
    coordinator = ActivityEvaluationCoordinator(
        MagicMock(),
        _entry(),
        client,
        _fitness(
            (
                _activity(
                    123,
                    duration_minutes=7.1,
                    aerobic_te=2.3,
                    anaerobic_te=0.4,
                    max_hr=151.0,
                ),
            )
        ),
        body,
    )

    data = await coordinator._async_update_data()
    selected = data["selected_evaluation"]

    assert selected["assessment_id"] == "short_aerobic"
    assert selected["estimated_vo2max"] is None
    assert selected["estimated_ftp_watts"] is None
    assert selected["detail_sample_count"] == 0


def test_selecting_an_existing_evaluation_updates_selected_payload() -> None:
    coordinator = ActivityEvaluationCoordinator(
        MagicMock(),
        _entry(),
        MagicMock(),
        _fitness(()),
        MagicMock(),
    )
    coordinator.data = {
        "evaluations": [
            {"activity_id": 2, "assessment_id": "aerobic_training"},
            {"activity_id": 1, "assessment_id": "recovery"},
        ],
        "selected_activity_id": 2,
        "selected_evaluation": {"activity_id": 2},
    }
    coordinator._selected_activity_id = 2

    coordinator.select_activity(1)

    assert coordinator.selected_activity_id == 1
    assert coordinator.data["selected_evaluation"]["activity_id"] == 1


def test_swedish_presentation_matches_locked_short_aerobic_copy() -> None:
    raw = {
        "activity_id": 123,
        "calendar_date": _DAY.isoformat(),
        "activity_type": "virtual_ride",
        "duration_minutes": 7.1,
        "title_key": "activity_eval_short_aerobic_title",
        "performance_confidence": "unavailable",
    }

    presented = present_activity_evaluation(raw, "sv-SE")

    assert presented["activity_name"] == "Virtuell cykling"
    assert presented["activity_icon"] == "mdi:bike"
    assert presented["title"] == "Kort aerobt pass"
    assert presented["message"] == (
        "Passet gav framför allt aerob träningseffekt med liten anaerob påverkan."
    )
    assert presented["confidence_label"] == "Saknas"
    assert activity_option_label(raw, "sv-SE", today=_DAY) == (
        "Idag · Virtuell cykling · 7 min"
    )


def test_activity_evaluation_sensor_exposes_localized_selected_pass() -> None:
    coordinator = MagicMock()
    coordinator.hass.config.language = "sv-SE"
    coordinator.last_update_success = True
    coordinator.data = {
        "ready": True,
        "status": "ready",
        "evaluation_count": 1,
        "selected_activity_id": 123,
        "selected_evaluation": {
            "activity_id": 123,
            "calendar_date": _DAY.isoformat(),
            "activity_type": "virtual_ride",
            "duration_minutes": 7.1,
            "assessment_id": "short_aerobic",
            "title_key": "activity_eval_short_aerobic_title",
            "message_key": "activity_eval_short_aerobic_message",
            "performance_confidence": "unavailable",
            "post_acwr": 0.57,
            "post_strain": 5.1,
            "post_tsb": 5.7,
        },
        "body_weight_kg": 70.0,
        "max_hr": 195.0,
        "limit": 5,
    }

    sensor = GarminActivityEvaluationSensor(coordinator, "entry_1")

    assert sensor.native_value == "short_aerobic"
    assert sensor.icon == "mdi:bike"
    attrs = sensor.extra_state_attributes
    assert attrs["title"] == "Kort aerobt pass"
    assert attrs["activity_name"] == "Virtuell cykling"
    assert attrs["post_acwr"] == 0.57
