"""Read-only Garmin Fitness activity-history probe.

This module intentionally works with the currently released ha-garmin API.
It uses the integration's existing authenticated GarminClient and performs no
login, writes, or Home Assistant Recorder changes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote

from ha_garmin import GarminClient
from ha_garmin.const import GARMIN_CONNECT_API

_PAGE_SIZE = 100
_MAX_PAGES = 50
_RECENT_ACTIVITY_LIMIT = 10
_USER_STATS_DAILY_URL = f"{GARMIN_CONNECT_API}/userstats-service/wellness/daily"
_RESTING_HR_METRIC_ID = 60
_RESTING_HR_METRIC_KEY = "WELLNESS_RESTING_HEART_RATE"
_ALGORITHM_VERSION = 1
_CTL_PERIOD_DAYS = 42
_ATL_PERIOD_DAYS = 7
_CTL_ALPHA = 2.0 / (_CTL_PERIOD_DAYS + 1.0)
_ATL_ALPHA = 2.0 / (_ATL_PERIOD_DAYS + 1.0)
_BANISTER_TRIMP_K_MALE = 1.92
_BANISTER_TRIMP_K_FEMALE = 1.67

Sex = Literal["male", "female"]


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


def _trimp_activity_inputs_ready(activity: dict[str, Any]) -> bool:
    """Return whether activity-level inputs required by TRIMP are present."""
    return (
        _number(activity.get("averageHR")) is not None
        and (_number(activity.get("duration")) or 0) > 0
    )


def _compute_trimp(
    activity: dict[str, Any],
    resting_hr: float,
    user_max_hr: float,
    sex: Sex,
) -> float | None:
    """Compute Banister TRIMP using the same v1 formula as ha-garmin Fitness."""
    avg_hr = _number(activity.get("averageHR"))
    duration_seconds = _number(activity.get("duration"))
    if avg_hr is None or duration_seconds is None or duration_seconds <= 0:
        return None
    if user_max_hr <= resting_hr:
        raise ValueError("max_hr must be greater than resting HR")

    hr_ratio = (avg_hr - resting_hr) / (user_max_hr - resting_hr)
    hr_ratio = max(0.0, min(1.0, hr_ratio))
    k = _BANISTER_TRIMP_K_FEMALE if sex == "female" else _BANISTER_TRIMP_K_MALE
    trimp = (duration_seconds / 60.0) * hr_ratio * math.exp(k * hr_ratio)
    return round(trimp, 3)


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


def _compact_activity(
    activity: dict[str, Any],
    resting_hr: dict[date, float],
    *,
    user_max_hr: float | None,
    sex: Sex | None,
) -> dict[str, Any]:
    """Return only Training-relevant fields; never include route/location data."""
    activity_date = _activity_date(activity)
    timestamp = _activity_timestamp(activity)
    duration = _number(activity.get("duration"))
    training_load = _number(activity.get("activityTrainingLoad"))
    avg_hr = _number(activity.get("averageHR"))
    max_hr = _number(activity.get("maxHR"))
    resting_hr_for_day = resting_hr.get(activity_date) if activity_date else None
    activity_inputs_ready = _trimp_activity_inputs_ready(activity)
    trimp_context_ready = activity_inputs_ready and resting_hr_for_day is not None
    trimp = None
    if (
        trimp_context_ready
        and resting_hr_for_day is not None
        and user_max_hr is not None
        and sex is not None
    ):
        trimp = _compute_trimp(activity, resting_hr_for_day, user_max_hr, sex)
    return {
        "activity_id": _activity_id(activity),
        "name": activity.get("activityName"),
        "activity_type": _activity_type(activity),
        "date": activity_date.isoformat() if activity_date else None,
        "start_time": timestamp.isoformat() if timestamp else None,
        "duration_minutes": round(duration / 60.0, 2) if duration is not None else None,
        "average_hr": avg_hr,
        "max_hr": max_hr,
        "resting_hr": resting_hr_for_day,
        "garmin_training_load": training_load,
        "trimp": trimp,
        "aerobic_training_effect": _number(activity.get("aerobicTrainingEffect")),
        "anaerobic_training_effect": _number(activity.get("anaerobicTrainingEffect")),
        "trimp_activity_inputs_ready": activity_inputs_ready,
        "trimp_context_ready": trimp_context_ready,
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


async def _fetch_resting_hr_window(
    client: GarminClient,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    """Fetch strict resting-HR measurements for the whole probe window."""
    profile = await client.get_user_profile()
    display_name = getattr(profile, "display_name", None)
    if not isinstance(display_name, str) or not display_name:
        raise RuntimeError("Garmin profile did not expose a valid display name")

    url = f"{_USER_STATS_DAILY_URL}/{quote(display_name, safe='')}"
    data = await client._request(
        "GET",
        url,
        params={
            "fromDate": start_date.isoformat(),
            "untilDate": end_date.isoformat(),
            "metricId": _RESTING_HR_METRIC_ID,
        },
    )
    if not data:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Garmin resting-HR history response")

    all_metrics = data.get("allMetrics")
    metrics_map = (
        all_metrics.get("metricsMap") if isinstance(all_metrics, dict) else None
    )
    raw_values = (
        metrics_map.get(_RESTING_HR_METRIC_KEY)
        if isinstance(metrics_map, dict)
        else None
    )
    if raw_values is None:
        return {}
    if not isinstance(raw_values, list):
        raise RuntimeError("Unexpected Garmin resting-HR metric response")

    result: dict[date, float] = {}
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("calendarDate")
        value = _number(item.get("value"))
        if not isinstance(raw_date, str) or value is None or value <= 0:
            continue
        try:
            measurement_date = date.fromisoformat(raw_date[:10])
        except ValueError:
            continue
        if start_date <= measurement_date <= end_date:
            result[measurement_date] = value
    return result


def _build_daily_loads(
    by_day: dict[date, list[dict[str, Any]]],
    resting_hr: dict[date, float],
    start_date: date,
    end_date: date,
    *,
    user_max_hr: float | None,
    sex: Sex | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build strict continuous Garmin Load and TRIMP daily series."""
    garmin_rows: list[dict[str, Any]] = []
    trimp_rows: list[dict[str, Any]] = []
    current = start_date
    while current <= end_date:
        items = by_day.get(current, [])
        if not items:
            garmin_rows.append({"date": current, "load": 0.0, "complete": True})
            trimp_rows.append({"date": current, "load": 0.0, "complete": True})
            current += timedelta(days=1)
            continue

        garmin_values = [
            value
            for item in items
            if (value := _number(item.get("activityTrainingLoad"))) is not None
        ]
        garmin_complete = len(garmin_values) == len(items)
        garmin_rows.append(
            {
                "date": current,
                "load": round(sum(garmin_values), 3) if garmin_complete else None,
                "known_load": round(sum(garmin_values), 3),
                "complete": garmin_complete,
            }
        )

        trimp_values: list[float] = []
        rhr = resting_hr.get(current)
        if rhr is not None and user_max_hr is not None and sex is not None:
            for item in items:
                value = _compute_trimp(item, rhr, user_max_hr, sex)
                if value is not None:
                    trimp_values.append(value)
        trimp_complete = (
            user_max_hr is not None
            and sex is not None
            and rhr is not None
            and len(trimp_values) == len(items)
        )
        trimp_rows.append(
            {
                "date": current,
                "load": round(sum(trimp_values), 3) if trimp_complete else None,
                "known_load": round(sum(trimp_values), 3),
                "complete": trimp_complete,
            }
        )
        current += timedelta(days=1)
    return garmin_rows, trimp_rows


def _training_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return CTL/ATL/TSB only when the whole daily series is complete."""
    blockers = [row["date"] for row in rows if not row["complete"] or row["load"] is None]
    if blockers:
        return {
            "ready": False,
            "blocker_dates": [item.isoformat() for item in blockers[:10]],
            "points": None,
            "latest": None,
        }
    if not rows:
        return {"ready": True, "blocker_dates": [], "points": [], "latest": None}

    first_load = float(rows[0]["load"])
    ctl = first_load
    atl = first_load
    points = [
        {
            "date": rows[0]["date"].isoformat(),
            "daily_load": first_load,
            "ctl": round(ctl, 3),
            "atl": round(atl, 3),
            "tsb": round(ctl - atl, 3),
        }
    ]
    for row in rows[1:]:
        load = float(row["load"])
        ctl = (_CTL_ALPHA * load) + ((1.0 - _CTL_ALPHA) * ctl)
        atl = (_ATL_ALPHA * load) + ((1.0 - _ATL_ALPHA) * atl)
        points.append(
            {
                "date": row["date"].isoformat(),
                "daily_load": load,
                "ctl": round(ctl, 3),
                "atl": round(atl, 3),
                "tsb": round(ctl - atl, 3),
            }
        )
    return {
        "ready": True,
        "blocker_dates": [],
        "points": points,
        "latest": points[-1],
    }


def _pearson(values_x: list[float], values_y: list[float]) -> float | None:
    """Return Pearson correlation for paired values without scipy."""
    if len(values_x) != len(values_y) or len(values_x) < 2:
        return None
    mean_x = sum(values_x) / len(values_x)
    mean_y = sum(values_y) / len(values_y)
    dx = [value - mean_x for value in values_x]
    dy = [value - mean_y for value in values_y]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denominator == 0:
        return None
    return round(sum(x * y for x, y in zip(dx, dy, strict=True)) / denominator, 3)


def _compare_daily_loads(
    garmin_rows: list[dict[str, Any]],
    trimp_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare complete activity-day loads where both source values exist."""
    garmin_values: list[float] = []
    trimp_values: list[float] = []
    paired_dates: list[str] = []
    for garmin_row, trimp_row in zip(garmin_rows, trimp_rows, strict=True):
        # Rest days are zero in both series and would artificially inflate correlation.
        if garmin_row["load"] == 0.0 and trimp_row["load"] == 0.0:
            continue
        if garmin_row["load"] is None or trimp_row["load"] is None:
            continue
        paired_dates.append(garmin_row["date"].isoformat())
        garmin_values.append(float(garmin_row["load"]))
        trimp_values.append(float(trimp_row["load"]))

    garmin_total = round(sum(garmin_values), 3)
    trimp_total = round(sum(trimp_values), 3)
    return {
        "paired_activity_days": len(paired_dates),
        "first_paired_date": paired_dates[0] if paired_dates else None,
        "last_paired_date": paired_dates[-1] if paired_dates else None,
        "pearson_correlation": _pearson(garmin_values, trimp_values),
        "garmin_load_total_on_paired_days": garmin_total,
        "trimp_total_on_paired_days": trimp_total,
        "trimp_to_garmin_total_ratio": (
            round(trimp_total / garmin_total, 3) if garmin_total > 0 else None
        ),
        "note": "Load scales differ; correlation compares shape, not numerical equivalence.",
    }


async def build_fitness_probe(
    client: GarminClient,
    days: int = 90,
    *,
    end_date: date | None = None,
    user_max_hr: float | None = None,
    sex: Sex | None = None,
) -> dict[str, Any]:
    """Return read-only Garmin Load/TRIMP diagnostics for a date window."""
    if days < 1 or days > 365:
        raise ValueError("days must be between 1 and 365")
    if (user_max_hr is None) != (sex is None):
        raise ValueError("max_hr and sex must be provided together")
    if user_max_hr is not None and not 100 <= user_max_hr <= 250:
        raise ValueError("max_hr must be between 100 and 250")
    if sex not in (None, "male", "female"):
        raise ValueError("sex must be male or female")

    end_date = end_date or date.today()
    start_date = end_date - timedelta(days=days - 1)
    activities, request_count = await _fetch_activity_window(client, start_date, end_date)
    resting_hr = await _fetch_resting_hr_window(client, start_date, end_date)

    total = len(activities)
    garmin_with_load = sum(
        _number(item.get("activityTrainingLoad")) is not None for item in activities
    )
    trimp_ready = sum(_trimp_activity_inputs_ready(item) for item in activities)

    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for item in activities:
        counts = by_type[_activity_type(item)]
        counts[0] += 1
        if _number(item.get("activityTrainingLoad")) is not None:
            counts[1] += 1
        if _trimp_activity_inputs_ready(item):
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

    activity_days_with_resting_hr = sum(day in resting_hr for day in by_day)
    complete_trimp_days = sum(
        day in resting_hr and all(_trimp_activity_inputs_ready(item) for item in items)
        for day, items in by_day.items()
    )
    incomplete_trimp_days = sorted(
        (
            day
            for day, items in by_day.items()
            if day not in resting_hr
            or any(not _trimp_activity_inputs_ready(item) for item in items)
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

    garmin_daily, trimp_daily = _build_daily_loads(
        by_day,
        resting_hr,
        start_date,
        end_date,
        user_max_hr=user_max_hr,
        sex=sex,
    )
    trimp_configured = user_max_hr is not None and sex is not None
    comparison = (
        _compare_daily_loads(garmin_daily, trimp_daily) if trimp_configured else None
    )
    compact = [
        _compact_activity(
            item,
            resting_hr,
            user_max_hr=user_max_hr,
            sex=sex,
        )
        for item in activities[:_RECENT_ACTIVITY_LIMIT]
    ]
    remaining_requirements = [] if trimp_configured else ["explicit max_hr", "sex"]
    return {
        "probe_version": 3,
        "algorithm_version": _ALGORITHM_VERSION,
        "read_only": True,
        "window": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "configuration": {
            "max_hr": user_max_hr,
            "sex": sex,
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
        },
        "resting_hr": {
            "measurement_days": len(resting_hr),
            "activity_days_with_measurement": activity_days_with_resting_hr,
            "activity_day_coverage_percent": (
                round(activity_days_with_resting_hr / activity_days * 100.0, 1)
                if activity_days
                else 0.0
            ),
        },
        "trimp_context": {
            "complete_activity_days": complete_trimp_days,
            "incomplete_activity_days": len(incomplete_trimp_days),
            "coverage_percent": (
                round(complete_trimp_days / activity_days * 100.0, 1)
                if activity_days
                else 0.0
            ),
            "first_incomplete_dates": [
                item.isoformat() for item in incomplete_trimp_days[:10]
            ],
            "remaining_requirements": remaining_requirements,
        },
        "comparison": comparison,
        "training_series": {
            "garmin": _training_series(garmin_daily),
            "trimp": _training_series(trimp_daily) if trimp_configured else None,
        },
        "by_activity_type": by_type_rows,
        "latest_activity": compact[0] if compact else None,
        "recent_activities": compact,
    }
