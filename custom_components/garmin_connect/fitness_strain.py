"""Compatibility wrappers for Garmin Fitness strain helpers.

All Fitness math lives in :mod:`ha_garmin.fitness`. This module keeps the
integration-facing calibration metadata/API stable while delegating TRIMP and
strain calculations to the library.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ha_garmin import GarminClient, GarminHistoryClient
from ha_garmin.fitness import (
    Sex,
    calibrate_personal_trimp_max,
    compute_trimp,
)
from ha_garmin.fitness import (
    compute_strain_score as _compute_strain_score,
)

from .const import (
    FITNESS_DEFAULT_PERSONAL_TRIMP_MAX,
    FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
    FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
)


def compute_strain_score(
    trimp: float,
    personal_trimp_max: float = FITNESS_DEFAULT_PERSONAL_TRIMP_MAX,
) -> float:
    """Delegate the bounded strain presentation score to ha-garmin Fitness."""
    return _compute_strain_score(trimp, personal_trimp_max)


def build_strain_calibration(session_trimps: list[float]) -> dict[str, Any]:
    """Return personal TRIMP-max calibration metadata from positive sessions."""
    values = [float(value) for value in session_trimps if value > 0]
    calibrated_value = calibrate_personal_trimp_max(
        values,
        min_sessions=FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        multiplier=FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
    )
    calibrated = calibrated_value is not None
    return {
        "personal_trimp_max": (
            calibrated_value
            if calibrated_value is not None
            else FITNESS_DEFAULT_PERSONAL_TRIMP_MAX
        ),
        "personal_trimp_max_source": "calibrated" if calibrated else "default",
        "strain_calibration_sessions": len(values),
        "strain_calibration_min_sessions": FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        "strain_calibration_multiplier": FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
        "strain_calibration_complete": True,
    }


def default_strain_calibration(*, complete: bool = False) -> dict[str, Any]:
    """Return explicit default metadata when calibration history is unavailable."""
    return {
        "personal_trimp_max": FITNESS_DEFAULT_PERSONAL_TRIMP_MAX,
        "personal_trimp_max_source": "default" if complete else "default_unavailable",
        "strain_calibration_sessions": 0 if complete else None,
        "strain_calibration_min_sessions": FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        "strain_calibration_multiplier": FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
        "strain_calibration_complete": complete,
    }


async def async_fetch_strain_calibration(
    client: GarminClient,
    start_date: date,
    end_date: date,
    *,
    user_max_hr: float,
    sex: Sex,
) -> dict[str, Any]:
    """Fetch one strict context and calibrate from activity-level TRIMP sessions."""
    context = await GarminHistoryClient(client).fetch_trimp_training_context(
        start_date,
        end_date,
        user_max_hr=user_max_hr,
        sex=sex,
    )

    session_trimps: list[float] = []
    for activity in context.activities:
        resting_hr = context.resting_hr_by_date.get(activity.calendar_date)
        if resting_hr is None:
            continue
        value = compute_trimp(activity, resting_hr, user_max_hr, sex)
        if value is not None and value > 0:
            session_trimps.append(value)

    return build_strain_calibration(session_trimps)
