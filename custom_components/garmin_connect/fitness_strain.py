"""TRIMP-derived strain helpers for Garmin Fitness.

This temporary Home Assistant adapter mirrors the Fitness core strain rules
without changing canonical TRIMP load. Personal calibration uses positive
activity-level TRIMP sessions; daily strain is then derived from the daily
TRIMP load on a bounded 0-21 scale.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from ha_garmin import GarminClient

from .const import (
    FITNESS_DEFAULT_PERSONAL_TRIMP_MAX,
    FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
    FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
    FITNESS_STRAIN_SCALE_MAX,
)
from .fitness_probe import (
    Sex,
    _activity_date,
    _compute_trimp,
    _enrich_incomplete_activity_inputs,
    _fetch_activity_window,
    _fetch_resting_hr_window,
)


def compute_strain_score(
    trimp: float,
    personal_trimp_max: float = FITNESS_DEFAULT_PERSONAL_TRIMP_MAX,
) -> float:
    """Convert TRIMP to the bounded 0-21 strain presentation scale."""
    if personal_trimp_max <= 0:
        raise ValueError("personal_trimp_max must be positive")
    if trimp <= 0:
        return 0.0

    score = FITNESS_STRAIN_SCALE_MAX * (
        1.0 - math.exp(-trimp / personal_trimp_max)
    )
    return round(min(FITNESS_STRAIN_SCALE_MAX, max(0.0, score)), 2)


def build_strain_calibration(session_trimps: list[float]) -> dict[str, Any]:
    """Return personal TRIMP-max calibration from positive session TRIMPs."""
    values = [float(value) for value in session_trimps if value > 0]
    calibrated = len(values) >= FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS
    personal_trimp_max = (
        round(max(values) * FITNESS_STRAIN_CALIBRATION_MULTIPLIER, 3)
        if calibrated
        else FITNESS_DEFAULT_PERSONAL_TRIMP_MAX
    )
    return {
        "personal_trimp_max": personal_trimp_max,
        "personal_trimp_max_source": "calibrated" if calibrated else "default",
        "strain_calibration_sessions": len(values),
        "strain_calibration_min_sessions": FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        "strain_calibration_multiplier": FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
        "strain_calibration_complete": True,
    }


def default_strain_calibration(*, complete: bool = False) -> dict[str, Any]:
    """Return an explicit default calibration when session history is unavailable."""
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
    """Fetch the effective window and calibrate from activity-level TRIMP sessions.

    This runs at most once per effective calculation window/day in the
    coordinator cache. It deliberately uses activity-level TRIMP rather than
    daily aggregate load so multiple sessions on one day remain distinct.
    """
    activities, _ = await _fetch_activity_window(client, start_date, end_date)
    await _enrich_incomplete_activity_inputs(client, activities)
    resting_hr = await _fetch_resting_hr_window(client, start_date, end_date)

    session_trimps: list[float] = []
    for activity in activities:
        activity_date = _activity_date(activity)
        if activity_date is None:
            continue
        rhr = resting_hr.get(activity_date)
        if rhr is None:
            continue
        trimp = _compute_trimp(activity, rhr, user_max_hr, sex)
        if trimp is not None and trimp > 0:
            session_trimps.append(trimp)

    return build_strain_calibration(session_trimps)
