"""Tests for the read-only Garmin Fitness activity probe."""

from datetime import date
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


@pytest.mark.asyncio
async def test_probe_reports_latest_rowing_and_coverage() -> None:
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

    result = await build_fitness_probe(
        client,
        days=30,
        end_date=date(2026, 9, 3),
    )

    assert result["activities"] == {
        "total": 3,
        "activity_days": 3,
        "rest_days": 27,
    }
    assert result["garmin_load"]["activities_with_load"] == 2
    assert result["garmin_load"]["coverage_percent"] == pytest.approx(66.7)
    assert result["trimp_activity_inputs"]["coverage_percent"] == 100.0
    assert result["latest_activity"]["activity_type"] == "indoor_rowing"
    assert result["latest_activity"]["garmin_training_load"] == 18.4
    assert result["latest_activity"]["duration_minutes"] == 15.0


@pytest.mark.asyncio
async def test_probe_stops_after_page_reaches_before_window() -> None:
    client = AsyncMock()
    page = [
        _activity(index + 1, "2026-09-03", load=1.0)
        for index in range(99)
    ]
    page.append(_activity(100, "2026-01-01", load=1.0))
    client.get_activities.return_value = page

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
async def test_probe_rejects_invalid_window() -> None:
    client = AsyncMock()

    with pytest.raises(ValueError, match="between 1 and 365"):
        await build_fitness_probe(client, days=0)
