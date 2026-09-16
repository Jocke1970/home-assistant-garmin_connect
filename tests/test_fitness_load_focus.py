"""Tests for Training Effect-derived Garmin Fitness load focus."""

from custom_components.garmin_connect.fitness_load_focus import (
    build_load_focus_day,
    compute_load_focus_contribution,
)


def test_load_focus_contribution_splits_aerobic_at_threshold() -> None:
    low = compute_load_focus_contribution(2.5, 0.4)
    high = compute_load_focus_contribution(3.2, 1.8)

    assert low == {
        "low_aerobic": 2.5,
        "high_aerobic": 0.0,
        "anaerobic": 0.4,
    }
    assert high == {
        "low_aerobic": 0.0,
        "high_aerobic": 3.2,
        "anaerobic": 1.8,
    }


def test_load_focus_day_preserves_missing_training_effect() -> None:
    result = build_load_focus_day([(2.5, 0.2), (4.0, None)])

    assert result["complete"] is False
    assert result["activity_count"] == 2
    assert result["covered_activities"] == 1
    assert result["missing_activities"] == 1
    assert result["low_aerobic"] is None
    assert result["high_aerobic"] is None
    assert result["anaerobic"] is None
    assert result["known_low_aerobic"] == 2.5
    assert result["known_high_aerobic"] == 0.0
    assert result["known_anaerobic"] == 0.2


def test_load_focus_rest_day_is_complete_zero() -> None:
    result = build_load_focus_day([])

    assert result["complete"] is True
    assert result["activity_count"] == 0
    assert result["low_aerobic"] == 0.0
    assert result["high_aerobic"] == 0.0
    assert result["anaerobic"] == 0.0
