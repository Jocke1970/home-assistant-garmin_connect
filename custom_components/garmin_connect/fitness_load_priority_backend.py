"""Read-only Load Priority backend; never feeds canonical Fitness or budgets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from ha_garmin.fitness.load_priority_preview import (
    DEFAULT_LOAD_PRIORITY,
    SPORT_FAMILY,
    LoadMethod,
    preview_activity_load,
)
from ha_garmin.history import TrimpTrainingContext

FitnessSex = Literal["male", "female"]


def build_load_priority_report(
    context: TrimpTrainingContext,
    *,
    user_max_hr: float,
    sex: FitnessSex,
    limit: int = 10,
    sport: str | None = None,
    priority: Sequence[LoadMethod] | None = None,
    override: LoadMethod | None = None,
    ftp_watts: float | None = None,
    threshold_speed_mps: float | None = None,
) -> dict[str, Any]:
    """Report a single selected source per activity from already-cached history.

    HR TRIMP, power TSS, Garmin Load and the pace proxy have different units.
    They must not be summed, backfilled or fed into training recommendations.
    """
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")
    if sport is not None and sport not in DEFAULT_LOAD_PRIORITY:
        raise ValueError("Unknown sport family")
    if priority is not None and sport is None:
        raise ValueError("sport is required for a custom priority")
    if override is not None and sport is None:
        raise ValueError("sport is required for an activity override")

    profiles = {sport: tuple(priority)} if sport is not None and priority is not None else None
    reports: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    unavailable = 0
    matching = 0

    # Normalization provides chronological activities. Most recent first for HA.
    for activity in reversed(context.activities):
        activity_sport = SPORT_FAMILY.get(activity.activity_type, "other")
        if sport is not None and activity_sport != sport:
            continue
        matching += 1
        if len(reports) >= limit:
            continue

        result = preview_activity_load(
            activity,
            profiles=profiles,
            resting_hr=context.resting_hr_by_date.get(activity.calendar_date),
            user_max_hr=user_max_hr,
            sex=sex,
            ftp_watts=ftp_watts,
            threshold_speed_mps=threshold_speed_mps,
            override=override,
        )
        selected = result.selected_method
        if selected is None:
            unavailable += 1
        else:
            selected_counts[selected] = selected_counts.get(selected, 0) + 1
        reports.append(
            {
                "activity_id": result.activity_id,
                "date": activity.calendar_date.isoformat(),
                "activity_type": activity.activity_type,
                "sport": result.sport,
                "priority": list(result.priority),
                "selected_source": selected,
                "load": result.value,
                "unit": result.unit,
                "canonical_compatible": result.canonical_compatible,
                "attempts": [
                    {
                        "source": attempt.method,
                        "available": attempt.available,
                        "reason": attempt.reason,
                    }
                    for attempt in result.attempts
                ],
            }
        )

    return {
        "preview_version": 1,
        "read_only": True,
        "canonical_series": "banister_trimp",
        "canonical_history_modified": False,
        "budget_modified": False,
        "mixed_units_must_not_be_summed": True,
        "sport_filter": sport,
        "matched_activities": matching,
        "returned_activities": len(reports),
        "unavailable_in_returned": unavailable,
        "selected_sources_in_returned": selected_counts,
        "activities": reports,
    }
