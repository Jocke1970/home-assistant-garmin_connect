"""Training Effect-derived load focus helpers for Garmin Fitness.

This is a transparent approximation of training mix, not Garmin's proprietary
Load Focus algorithm. Garmin Aerobic Training Effect contributes to either the
low- or high-aerobic bucket, while Anaerobic Training Effect contributes to the
anaerobic bucket independently. No TRIMP or Garmin training-load weighting is
used. The aerobic split threshold is part of this integration's versioned v1
heuristic and is exposed as provenance rather than presented as a Garmin rule.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from .const import FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD


def _finite_nonnegative(value: Any) -> float | None:
    """Return a finite non-negative number, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def compute_load_focus_contribution(
    aerobic_training_effect: Any,
    anaerobic_training_effect: Any,
    *,
    high_aerobic_threshold: float = FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
) -> dict[str, float] | None:
    """Return one activity's low/high aerobic and anaerobic TE contributions.

    Both Garmin Training Effect values must be present. Missing data returns
    ``None`` so callers can preserve an incomplete day instead of fabricating a
    zero contribution.
    """
    if high_aerobic_threshold <= 0:
        raise ValueError("high_aerobic_threshold must be positive")

    aerobic = _finite_nonnegative(aerobic_training_effect)
    anaerobic = _finite_nonnegative(anaerobic_training_effect)
    if aerobic is None or anaerobic is None:
        return None

    low_aerobic = aerobic if 0 < aerobic < high_aerobic_threshold else 0.0
    high_aerobic = aerobic if aerobic >= high_aerobic_threshold else 0.0
    return {
        "low_aerobic": round(low_aerobic, 3),
        "high_aerobic": round(high_aerobic, 3),
        "anaerobic": round(anaerobic, 3),
    }


def build_load_focus_day(
    training_effects: Iterable[tuple[Any, Any]],
    *,
    high_aerobic_threshold: float = FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
) -> dict[str, Any]:
    """Aggregate one calendar day's Training Effect contributions.

    A rest day is a complete zero day. If any activity lacks either Training
    Effect value, the canonical bucket values are ``None`` for that day while
    known partial totals remain available for diagnostics.
    """
    effects = list(training_effects)
    low_aerobic = 0.0
    high_aerobic = 0.0
    anaerobic = 0.0
    covered = 0

    for aerobic, anaerobic_effect in effects:
        contribution = compute_load_focus_contribution(
            aerobic,
            anaerobic_effect,
            high_aerobic_threshold=high_aerobic_threshold,
        )
        if contribution is None:
            continue
        covered += 1
        low_aerobic += contribution["low_aerobic"]
        high_aerobic += contribution["high_aerobic"]
        anaerobic += contribution["anaerobic"]

    complete = covered == len(effects)
    known_low = round(low_aerobic, 3)
    known_high = round(high_aerobic, 3)
    known_anaerobic = round(anaerobic, 3)
    return {
        "complete": complete,
        "activity_count": len(effects),
        "covered_activities": covered,
        "missing_activities": len(effects) - covered,
        "low_aerobic": known_low if complete else None,
        "high_aerobic": known_high if complete else None,
        "anaerobic": known_anaerobic if complete else None,
        "known_low_aerobic": known_low,
        "known_high_aerobic": known_high,
        "known_anaerobic": known_anaerobic,
    }
