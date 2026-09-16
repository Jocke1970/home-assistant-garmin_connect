"""Tests for Garmin Fitness strain helpers."""

from custom_components.garmin_connect.fitness_strain import (
    build_strain_calibration,
    compute_strain_score,
    default_strain_calibration,
)


def test_compute_strain_score_matches_fitness_core_curve() -> None:
    assert compute_strain_score(0.0) == 0.0
    assert compute_strain_score(100.0, 250.0) == 6.92
    assert 0.0 <= compute_strain_score(100000.0, 250.0) <= 21.0


def test_strain_calibration_requires_30_positive_sessions() -> None:
    sparse = build_strain_calibration([float(value) for value in range(1, 30)])
    assert sparse["personal_trimp_max"] == 250.0
    assert sparse["personal_trimp_max_source"] == "default"
    assert sparse["strain_calibration_sessions"] == 29
    assert sparse["strain_calibration_complete"] is True

    calibrated = build_strain_calibration([float(value) for value in range(1, 31)])
    assert calibrated["personal_trimp_max"] == 36.0
    assert calibrated["personal_trimp_max_source"] == "calibrated"
    assert calibrated["strain_calibration_sessions"] == 30
    assert calibrated["strain_calibration_min_sessions"] == 30
    assert calibrated["strain_calibration_multiplier"] == 1.2


def test_default_strain_calibration_distinguishes_unavailable_history() -> None:
    unavailable = default_strain_calibration(complete=False)
    assert unavailable["personal_trimp_max"] == 250.0
    assert unavailable["personal_trimp_max_source"] == "default_unavailable"
    assert unavailable["strain_calibration_sessions"] is None
    assert unavailable["strain_calibration_complete"] is False
