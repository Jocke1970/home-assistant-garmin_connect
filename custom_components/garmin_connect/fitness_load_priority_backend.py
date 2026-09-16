"""Read-only Load Priority backend; never feeds canonical Fitness or budgets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from ha_garmin.fitness.load_priority_preview import (
    DEFAULT_LOAD_PRIORITY,
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
    """Evaluate already-cached Garmin activities without changing training history.

    A result represents exactly one unit from exactly one source per activity.
    Never sum these results across methods, export them as TRIMP or update CTL,
    ATL, ACWR, Strain, Ramp or the daily training budget.
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
        # The selector owns the mapping of raw Garmin activity types to sports.
        result = preview_activity_load(
            activity,
            profiles=profiles,
            resting_hr=context.resting_hr_by_date.get(activity.calendar_date),
            user_max_hr=user_max_hr,
            sex=sex,
            ftp_watts=ftp_watts,
            threshold_speed_mps=threshold_speed_mps,
            override=override if sport is not None else None,
        ) if sport is None else None
        if sport is not None:
            # Restrict the override to the requested sport only. Do not let a
            # one-off preview change how other activities are interpreted.
            from ha_garmin.fitness.load_priority_preview import SPORT_FAMILY

            if SPORT_FAMILY.get(activity.activity_type, "other") != sport:
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
        assert result is not None
        matching += 1
        if len(reports) >= limit:
            continue
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
