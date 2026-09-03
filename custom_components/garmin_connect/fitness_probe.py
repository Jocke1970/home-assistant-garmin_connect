"""Read-only Garmin Fitness activity-history probe.

This module intentionally works with the currently released ha-garmin API.
It uses the integration's existing authenticated GarminClient and performs no
login, writes, or Home Assistant Recorder changes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ha_garmin import GarminClient

_PAGE_SIZE = 100
_MAX_PAGES = 50
_RECENT_ACTIVITY_LIMIT = 10


def _number(value: Any) -> float | None:
    """Return a finite numeric value, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _activity_date(activity: dict[str, Any]) -> date | None:
    """Return Garmin's local calendar date when possible."""
    raw_calendar = activity.get("calendarDate")
    if isinstance(raw_calendar, date) and not isinstance(raw_calendar, datetime):
        return raw_calendar
    if isinstance(raw_calendar, str):
        try:
            return date.fromisoformat(raw_calendar[:10])
        except ValueError:
            pass

    for key in ("startTimeLocal", "startTime", "startTimeGMT"):
        value = activity.get(key)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                continue
    return None


def _activity_timestamp(activity: dict[str, Any]) -> datetime | None:
    """Return the best available timestamp for ordering/reporting."""
    for key, assume_utc in (
        ("startTimeLocal", False),
        ("startTime", False),
        ("startTimeGMT", True),
    ):
        value = activity.get(key)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if assume_utc and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
    return None


def _activity_type(activity: dict[str, Any]) -> str:
    """Normalize Garmin's activityType shape."""
    value = activity.get("activityType")
    if isinstance(value, dict):
        value = value.get("typeKey")
    return str(value or "unknown")


def _activity_id(activity: dict[str, Any]) -> int | None:
    value = activity.get("activityId")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        result = int(value)
    except ValueError:
        return None
    return result if result > 0 else None


def _richness(activity: dict[str, Any]) -> int:
    """Score fields useful to Training calculations for duplicate selection."""
    fields = (
        "activityTrainingLoad",
        "averageHR",
        "maxHR",
        "duration",
        "aerobicTrainingEffect",
        "anaerobicTrainingEffect",
        "vO2MaxValue",
        "avgPower",
        "normPower",
    )
    return sum(activity.get(key) is not None for key in fields)


def _deduplicate(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate Garmin activities, preferring the calculation-richer record."""
    by_id: dict[int, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for activity in activities:
        activity_id = _activity_id(activity)
        if activity_id is None:
            anonymous.append(activity)
            continue
        current = by_id.get(activity_id)
        if current is None or _richness(activity) > _richness(current):
            by_id[activity_id] = activity
    return [*by_id.values(), *anonymous]


def _sort_key(activity: dict[str, Any]) -> tuple[date, datetime]:
    activity_date = _activity_date(activity) or date.min
    timestamp = _activity_timestamp(activity)
    if timestamp is None:
        timestamp = datetime.combine(activity_date, datetime.min.time())
    # Comparing aware and naive datetimes raises TypeError. Strip timezone only
    # for deterministic ordering; the original value is preserved for output.
    return activity_date, timestamp.replace(tzinfo=None)


def _compact_activity(activity: dict[str, Any]) -> dict[str, Any]:
    """Return only Training-relevant fields; never include route/location data."""
    activity_date = _activity_date(activity)
    timestamp = _activity_timestamp(activity)
    duration = _number(activity.get("duration"))
    training_load = _number(activity.get("activityTrainingLoad"))
    avg_hr = _number(activity.get("averageHR"))
    max_hr = _number(activity.get("maxHR"))
    return {
        "activity_id": _activity_id(activity),
        "name": activity.get("activityName"),
        "activity_type": _activity_type(activity),
        "date": activity_date.isoformat() if activity_date else None,
        "start_time": timestamp.isoformat() if timestamp else None,
        "duration_minutes": round(duration / 60.0, 2) if duration is not None else None,
        "average_hr": avg_hr,
        "max_hr": max_hr,
        "garmin_training_load": training_load,
        "aerobic_training_effect": _number(activity.get("aerobicTrainingEffect")),
        "anaerobic_training_effect": _number(activity.get("anaerobicTrainingEffect")),
        "trimp_activity_inputs_ready": avg_hr is not None
        and duration is not None
        and duration > 0,
    }


async def _fetch_activity_window(
    client: GarminClient,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch newest-first pages until the requested date window is covered."""
    collected: list[dict[str, Any]] = []
    requests = 0

    for page_index in range(_MAX_PAGES):
        page = await client.get_activities(
            start=page_index * _PAGE_SIZE,
            limit=_PAGE_SIZE,
        )
        requests += 1
        if not page:
            break

        valid_page_dates: list[date] = []
        for item in page:
            if not isinstance(item, dict):
                continue
            item_date = _activity_date(item)
            if item_date is not None:
                valid_page_dates.append(item_date)
                if start_date <= item_date <= end_date:
                    collected.append(item)

        # Garmin returns newest-first. Once a page reaches before the requested
        # window, later pages cannot contribute useful records.
        if valid_page_dates and min(valid_page_dates) < start_date:
            break

        if len(page) < _PAGE_SIZE:
            break
    else:
        raise RuntimeError(
            f"Garmin Fitness probe exceeded pagination safety limit ({_MAX_PAGES} pages)"
        )

    deduplicated = _deduplicate(collected)
    deduplicated.sort(key=_sort_key, reverse=True)
    return deduplicated, requests


async def build_fitness_probe(
    client: GarminClient,
    days: int = 90,
    *,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Return read-only Garmin Load/TRIMP-input diagnostics for a date window."""
    if days < 1 or days > 365:
        raise ValueError("days must be between 1 and 365")

    end_date = end_date or date.today()
    start_date = end_date - timedelta(days=days - 1)
    activities, request_count = await _fetch_activity_window(client, start_date, end_date)

    total = len(activities)
    garmin_with_load = sum(
        _number(item.get("activityTrainingLoad")) is not None for item in activities
    )
    trimp_ready = sum(
        _number(item.get("averageHR")) is not None
        and (_number(item.get("duration")) or 0) > 0
        for item in activities
    )

    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for item in activities:
        counts = by_type[_activity_type(item)]
        counts[0] += 1
        if _number(item.get("activityTrainingLoad")) is not None:
            counts[1] += 1
        if (
            _number(item.get("averageHR")) is not None
            and (_number(item.get("duration")) or 0) > 0
        ):
            counts[2] += 1
        item_date = _activity_date(item)
        if item_date is not None:
            by_day[item_date].append(item)

    activity_days = len(by_day)
    complete_garmin_days = sum(
        all(_number(item.get("activityTrainingLoad")) is not None for item in items)
        for items in by_day.values()
    )
    incomplete_days = sorted(
        (
            day
            for day, items in by_day.items()
            if any(_number(item.get("activityTrainingLoad")) is None for item in items)
        ),
        reverse=True,
    )

    by_type_rows = []
    for activity_type, (type_total, type_garmin, type_trimp) in sorted(by_type.items()):
        by_type_rows.append(
            {
                "activity_type": activity_type,
                "activities": type_total,
                "garmin_load_activities": type_garmin,
                "garmin_load_percent": round(type_garmin / type_total * 100.0, 1),
                "trimp_input_activities": type_trimp,
                "trimp_input_percent": round(type_trimp / type_total * 100.0, 1),
            }
        )

    compact = [_compact_activity(item) for item in activities[:_RECENT_ACTIVITY_LIMIT]]
    return {
        "probe_version": 1,
        "read_only": True,
        "window": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "api_requests": request_count,
        "activities": {
            "total": total,
            "activity_days": activity_days,
            "rest_days": days - activity_days,
        },
        "garmin_load": {
            "activities_with_load": garmin_with_load,
            "activities_without_load": total - garmin_with_load,
            "coverage_percent": (
                round(garmin_with_load / total * 100.0, 1) if total else 0.0
            ),
            "complete_activity_days": complete_garmin_days,
            "incomplete_activity_days": len(incomplete_days),
            "first_incomplete_dates": [item.isoformat() for item in incomplete_days[:10]],
        },
        "trimp_activity_inputs": {
            "eligible_activities": trimp_ready,
            "ineligible_activities": total - trimp_ready,
            "coverage_percent": round(trimp_ready / total * 100.0, 1) if total else 0.0,
            "note": "Full TRIMP also requires resting HR plus explicit max HR and sex.",
        },
        "by_activity_type": by_type_rows,
        "latest_activity": compact[0] if compact else None,
        "recent_activities": compact,
    }
