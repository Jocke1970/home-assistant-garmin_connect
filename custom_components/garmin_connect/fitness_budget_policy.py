"""Priority-aware planning budget for Garmin Fitness.

This module deliberately keeps the canonical TRIMP history untouched.  It only
builds a synthetic *planning* history for today's budget where clearly
low-intensity activities can be excluded from budget consumption.  The actual
Fitness metrics (CTL/ATL/TSB/ACWR/Strain) continue to use the canonical history.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Literal

from ha_garmin.fitness import compute_trimp, recommend_daily_load_budget
from ha_garmin.fitness.load_priority_preview import preview_activity_load
from ha_garmin.fitness.pipeline import build_training_history_from_daily_loads
from ha_garmin.history import TrimpTrainingContext

FitnessSex = Literal["male", "female"]

# Conservative planning-only thresholds.  They classify whether an activity is
# sufficiently easy to stay outside the finite training budget; they do not
# change the canonical Fitness calculations.
LOW_INTENSITY_POWER_IF_MAX = 0.75
LOW_INTENSITY_HRR_MAX = 0.60
LOW_INTENSITY_PACE_RATIO_MAX = 0.80
LOW_INTENSITY_GARMIN_TE_MAX = 2.0


def _activity_intensity(
    *,
    selected_source: str | None,
    activity: Any,
    resting_hr: float | None,
    user_max_hr: float,
    ftp_watts: float | None,
    threshold_speed_mps: float | None,
) -> tuple[str, float | None, str]:
    """Return low/training/unknown plus a transparent intensity ratio."""
    if selected_source == "power":
        if (
            activity.normalized_power is None
            or ftp_watts is None
            or ftp_watts <= 0
        ):
            return "unknown", None, "power_context_unavailable"
        ratio = activity.normalized_power / ftp_watts
        return (
            "low" if ratio <= LOW_INTENSITY_POWER_IF_MAX else "training",
            round(ratio, 3),
            "power_if",
        )

    if selected_source == "hr":
        if (
            activity.avg_hr is None
            or resting_hr is None
            or user_max_hr <= resting_hr
        ):
            return "unknown", None, "hr_context_unavailable"
        ratio = (activity.avg_hr - resting_hr) / (user_max_hr - resting_hr)
        ratio = max(0.0, min(1.0, ratio))
        return (
            "low" if ratio <= LOW_INTENSITY_HRR_MAX else "training",
            round(ratio, 3),
            "heart_rate_reserve",
        )

    if selected_source == "pace":
        if (
            activity.distance_meters is None
            or activity.duration_minutes <= 0
            or threshold_speed_mps is None
            or threshold_speed_mps <= 0
        ):
            return "unknown", None, "pace_context_unavailable"
        speed_mps = activity.distance_meters / (activity.duration_minutes * 60.0)
        ratio = speed_mps / threshold_speed_mps
        return (
            "low" if ratio <= LOW_INTENSITY_PACE_RATIO_MAX else "training",
            round(ratio, 3),
            "pace_ratio",
        )

    if selected_source == "garmin":
        values = [
            value
            for value in (
                activity.aerobic_training_effect,
                activity.anaerobic_training_effect,
            )
            if value is not None
        ]
        if not values:
            return "unknown", None, "training_effect_unavailable"
        training_effect = max(values)
        return (
            "low" if training_effect <= LOW_INTENSITY_GARMIN_TE_MAX else "training",
            round(training_effect, 3),
            "garmin_training_effect",
        )

    return "unknown", None, "load_source_unavailable"


def build_priority_aware_daily_budget(
    context: TrimpTrainingContext,
    personal_trimp_max: float,
    *,
    user_max_hr: float,
    sex: FitnessSex,
    insight_result_ids: tuple[str, ...] = (),
    ftp_watts: float | None = None,
    threshold_speed_mps: float | None = None,
) -> dict[str, Any]:
    """Build today's planning budget without charging clearly easy activity.

    The selected source follows the per-sport Load Priority defaults.  Source
    choice is used for *classification*.  Because the canonical budget scale is
    still Banister TRIMP, any excluded load is calculated as TRIMP before being
    removed from today's synthetic planning history.  This avoids mixing TSS,
    TRIMP, Garmin Load and the pace proxy in one series.
    """
    if not context.history.daily_loads:
        raise ValueError("Training history is empty")
    if not context.history.assessment.ready:
        raise ValueError("Training history is incomplete")

    target_date = context.history.daily_loads[-1].date
    canonical_today = context.history.daily_loads[-1]
    canonical_current_load = float(canonical_today.load or 0.0)

    excluded_low_load = 0.0
    low_intensity_count = 0
    training_count = 0
    unknown_count = 0
    decisions: list[dict[str, Any]] = []

    for activity in context.activities:
        if activity.calendar_date != target_date:
            continue
        resting_hr = context.resting_hr_by_date.get(activity.calendar_date)
        selected = preview_activity_load(
            activity,
            resting_hr=resting_hr,
            user_max_hr=user_max_hr,
            sex=sex,
            ftp_watts=ftp_watts,
            threshold_speed_mps=threshold_speed_mps,
        )
        intensity, intensity_value, intensity_basis = _activity_intensity(
            selected_source=selected.selected_method,
            activity=activity,
            resting_hr=resting_hr,
            user_max_hr=user_max_hr,
            ftp_watts=ftp_watts,
            threshold_speed_mps=threshold_speed_mps,
        )

        canonical_trimp: float | None = None
        if resting_hr is not None:
            canonical_trimp = compute_trimp(
                activity,
                resting_hr,
                user_max_hr,
                sex,
            )

        if intensity == "low" and canonical_trimp is not None:
            excluded_low_load += canonical_trimp
            low_intensity_count += 1
        elif intensity == "training":
            training_count += 1
        else:
            unknown_count += 1

        decisions.append(
            {
                "activity_id": activity.activity_id,
                "activity_type": activity.activity_type,
                "sport": selected.sport,
                "priority": list(selected.priority),
                "selected_source": selected.selected_method,
                "selected_load": selected.value,
                "selected_unit": selected.unit,
                "intensity_lane": intensity,
                "intensity_value": intensity_value,
                "intensity_basis": intensity_basis,
                "canonical_trimp": canonical_trimp,
            }
        )

    excluded_low_load = round(min(excluded_low_load, canonical_current_load), 3)
    budget_consuming_load = round(
        max(0.0, canonical_current_load - excluded_low_load),
        3,
    )

    planning_days = list(context.history.daily_loads)
    planning_days[-1] = replace(
        canonical_today,
        known_load=budget_consuming_load,
        load=budget_consuming_load,
    )
    planning_history = build_training_history_from_daily_loads(
        "trimp",
        planning_days,
    )
    budget = recommend_daily_load_budget(
        planning_history,
        personal_trimp_max,
        insight_result_ids=insight_result_ids,
    )

    result = asdict(budget)
    result.update(
        {
            "planning_policy_version": 2,
            "planning_mode": "load_priority",
            "canonical_history_modified": False,
            "canonical_current_load": round(canonical_current_load, 3),
            "budget_consuming_load": budget_consuming_load,
            "excluded_low_intensity_load": excluded_low_load,
            "low_intensity_activity_count": low_intensity_count,
            "training_activity_count": training_count,
            "unknown_intensity_activity_count": unknown_count,
            "activity_decisions": decisions,
            "load_priority_defaults": True,
            "low_intensity_thresholds": {
                "power_if_max": LOW_INTENSITY_POWER_IF_MAX,
                "heart_rate_reserve_max": LOW_INTENSITY_HRR_MAX,
                "pace_ratio_max": LOW_INTENSITY_PACE_RATIO_MAX,
                "garmin_training_effect_max": LOW_INTENSITY_GARMIN_TE_MAX,
            },
        }
    )
    return result
