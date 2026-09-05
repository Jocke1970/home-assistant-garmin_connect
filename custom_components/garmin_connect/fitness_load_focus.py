"""Compatibility wrappers for Garmin Fitness load-focus helpers.

The calculation lives in :mod:`ha_garmin.fitness`; Home Assistant keeps these
wrappers only so existing integration tests/imports retain a stable module path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ha_garmin.fitness import (
    build_load_focus_day as _build_load_focus_day,
    compute_load_focus_contribution as _compute_load_focus_contribution,
)

from .const import FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD


def compute_load_focus_contribution(
    aerobic_training_effect: Any,
    anaerobic_training_effect: Any,
    *,
    high_aerobic_threshold: float = FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
) -> dict[str, float] | None:
    """Delegate one activity's TE contribution to ha-garmin Fitness."""
    return _compute_load_focus_contribution(
        aerobic_training_effect,
        anaerobic_training_effect,
        high_aerobic_threshold=high_aerobic_threshold,
    )


def build_load_focus_day(
    training_effects: Iterable[tuple[Any, Any]],
    *,
    high_aerobic_threshold: float = FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
) -> dict[str, Any]:
    """Delegate daily TE bucket aggregation to ha-garmin Fitness."""
    return _build_load_focus_day(
        training_effects,
        high_aerobic_threshold=high_aerobic_threshold,
    )
