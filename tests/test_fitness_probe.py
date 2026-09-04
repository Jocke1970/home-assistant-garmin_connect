"""Tests for the read-only Garmin Fitness activity probe."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.garmin_connect.fitness_probe import build_fitness_probe


def _activity(
    activity_id: int,
    day: str,
    *,
    activity_type: str = "walking",
    name: str = "Walk",
    load: float | None = None,
    avg_hr: float | None = 100,
    duration: float | None = 1800,
) -> dict:
    data = {
        "activityId": activity_id,
        "activityName": name,
        "activityType": {"typeKey": activity_type},
        "calendarDate": day,
        "startTimeLocal": f"{day}T18:00:00",
        "averageHR": avg_hr,
        "duration": duration,
    }
    if load is not None:
        data["activityTrainingLoad"] = load
    return data


def _configure_resting_hr(client: AsyncMock, values: dict[str, float]) -> None:
    client.get_user_profile.return_value = SimpleNamespace(display_name="test/user")
    client._request.return_value = {
        "allMetrics": {
            "metricsMap": {
                "WELLNESS_RESTING_HEART_RATE": [
                    {"calendarDate": day, "value": value}
                    for day, value in values.items()
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_probe_reports_trimp_comparison_and_series_readiness() -> None:
    client = AsyncMock()
    client.get_activities.side_effect = [
        [
            _activity(
                3,
                "2026-09-03",
                activity_type="indoor_rowing",
                name="Indoor rowing",
                load=18.4,
                avg_hr=128,
                duration=900,
            ),
            _activity(2, "2026-08-20", load=None, avg_hr=98),
            _activity(1, "2026-08-10", load=4.2, avg_hr=101),
        ]
    ]
    _configure_resting_hr(
        client,
        {"2026-09-03": 56, "2026-08-20": 58, "2026-08-10": 57},
    )

    result = await build_fitness_probe(
        client,
        days=30,
        end_date=date(2026, 9, 3),
        user_max_hr=175,
        sex="male",
    )

    assert result["probe_version"] == 4
    assert result["algorithm_version"] == 1
    assert result["configuration"] == {"max_hr": 175, "sex": "male"}
    assert result["activity_detail_requests"] == 0
    assert result["activities_repaired_from_detail"] == 0
    assert result["activities"] == {
        "total": 3,
        "activity_days": 3,
        "rest_days": 27,
    }
    assert result["garmin_load"]["activities_with_load"] == 2
    assert result["garmin_load"]["coverage_percent"] == pytest.approx(66.7)
    assert result["trimp_activity_inputs"]["coverage_percent"] == 100.0
    assert result["resting_hr"]["activity_day_coverage_percent"] == 100.0
    assert result["trimp_context"]["coverage_percent"] == 100.0
    assert result["trimp_context"]["blocker_activities"] == []
    assert result["trimp_context"]["remaining_requirements"] == []
    assert result["latest_activity"]["activity_type"] == "indoor_rowing"
    assert result["latest_activity"]["garmin_training_load"] == 18.4
    assert result["latest_activity"]["duration_minutes"] == 15.0
    assert result["latest_activity"]["resting_hr"] == 56
    assert result["latest_activity"]["trimp"] == pytest.approx(28.999)
    assert result["latest_activity"]["trimp_context_ready"] is True
    assert result["comparison"]["paired_activity_days"] == 2
    assert result["training_series"]["garmin"]["ready"] is False
    assert result["training_series"]["garmin"]["blocker_dates"] == ["2026-08-20"]
    assert result["training_series"]["trimp"]["ready"] is True
    assert len(result["training_series"]["trimp"]["points"]) == 30


@pytest.mark.asyncio
async def test_probe_repairs_missing_hr_from_single_activity_summary() -> None:
    """A sparse list row is enriched from Garmin before becoming a blocker."""
    client = AsyncMock()
    client.get_activities.return_value = [
        _activity(7, "2026-09-03", avg_hr=None, duration=1200),
    ]
    client.get_activity.return_value = {
        "summaryDTO": {
            "averageHR": 123,
            "duration": 1200,
            "maxHR": 141,
        }
    }
    _configure_resting_hr(client, {"2026-09-03": 55})

    result = await build_fitness_probe(
        client,
        days=1,
        end_date=date(2026, 9, 3),
        user_max_hr=175,
        sex="male",
    )

    client.get_activity.assert_awaited_once_with(7)
    assert result["activity_detail_requests"] == 1
    assert result["activities_repaired_from_detail"] == 1
    assert result["trimp_activity_inputs"]["coverage_percent"] == 100.0
    assert result["trimp_context"]["incomplete_activity_days"] == 0
    assert result["trimp_context"]["blocker_activities"] == []
    assert result["latest_activity"]["average_hr"] == 123.0
    assert result["latest_activity"]["max_hr"] == 141.0
    assert result["training_series"]["trimp"]["ready"] is True


@pytest.mark.asyncio
async def test_probe_reports_unresolved_blocker_activity() -> None:
    """If Garmin detail is also sparse, keep the day incomplete and expose why."""
    client = AsyncMock()
    client.get_activities.return_value = [
        _activity(8, "2026-09-03", avg_hr=None, duration=900),
    ]
    client.get_activity.return_value = {"summaryDTO": {"duration": 900}}
    _configure_resting_hr(client, {"2026-09-03": 55})

    result = await build_fitness_probe(
        client,
        days=1,
        end_date=date(2026, 9, 3),
        user_max_hr=175,
        sex="male",
    )

    assert result["activities_repaired_from_detail"] == 0
    assert result["trimp_context"]["incomplete_activity_days"] == 1
    assert result["trimp_context"]["first_incomplete_dates"] == ["2026-09-03"]
    blocker = result["trimp_context"]["blocker_activities"][0]
    assert blocker["activity_id"] == 8
    assert blocker["average_hr"] is None
    assert blocker["duration_minutes"] == 15.0
    assert blocker["trimp_activity_inputs_ready"] is False
    assert result["training_series"]["trimp"]["ready"] is False


@pytest.mark.asyncio
async def test_probe_stops_after_page_reaches_before_window() -> None:
    client = AsyncMock()
    page = [_activity(index + 1, "2026-09-03", load=1.0) for index in range(99)]
    page.append(_activity(100, "2026-01-01", load=1.0))
    client.get_activities.return_value = page
    _configure_resting_hr(client, {"2026-09-03": 55})

    result = await build_fitness_probe(
        client,
        days=30,
        end_date=date(2026, 9, 3),
    )

    assert result["api_requests"] == 1
    assert result["activities"]["total"] == 99
    client.get_activities.assert_awaited_once_with(start=0, limit=100)


@pytest.mark.asyncio
async def test_probe_prefers_richer_duplicate_activity() -> None:
    client = AsyncMock()
    client.get_activities.return_value = [
        _activity(42, "2026-09-03", load=None, avg_hr=120),
        {
            **_activity(42, "2026-09-03", load=12.5, avg_hr=120),
            "aerobicTrainingEffect": 2.1,
            "anaerobicTrainingEffect": 0.2,
        },
    ]
    _configure_resting_hr(client, {"2026-09-03": 54})

    result = await build_fitness_probe(
        client,
        days=1,
        end_date=date(2026, 9, 3),
    )

    assert result["activities"]["total"] == 1
    assert result["garmin_load"]["coverage_percent"] == 100.0
    assert result["latest_activity"]["garmin_training_load"] == 12.5
    assert result["latest_activity"]["aerobic_training_effect"] == 2.1


@pytest.mark.asyncio
async def test_probe_marks_missing_resting_hr_as_incomplete_trimp_context() -> None:
    client = AsyncMock()
    client.get_activities.return_value = [
        _activity(2, "2026-09-03", avg_hr=120),
        _activity(1, "2026-09-02", avg_hr=110),
    ]
    _configure_resting_hr(client, {"2026-09-02": 57})

    result = await build_fitness_probe(
        client,
        days=2,
        end_date=date(2026, 9, 3),
    )

    assert result["resting_hr"]["measurement_days"] == 1
    assert result["resting_hr"]["activity_day_coverage_percent"] == 50.0
    assert result["trimp_context"]["complete_activity_days"] == 1
    assert result["trimp_context"]["incomplete_activity_days"] == 1
    assert result["trimp_context"]["first_incomplete_dates"] == ["2026-09-03"]
    assert result["latest_activity"]["resting_hr"] is None
    assert result["latest_activity"]["trimp_context_ready"] is False


@pytest.mark.asyncio
async def test_probe_rejects_partial_trimp_configuration() -> None:
    client = AsyncMock()

    with pytest.raises(ValueError, match="provided together"):
        await build_fitness_probe(client, days=30, user_max_hr=175)


@pytest.mark.asyncio
async def test_probe_rejects_invalid_window() -> None:
    client = AsyncMock()

    with pytest.raises(ValueError, match="between 1 and 365"):
        await build_fitness_probe(client, days=0)
