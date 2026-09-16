"""Home Assistant presentation helpers for Garmin activity evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

PresentationLanguage = Literal["en", "sv"]

_ASSESSMENT_TEXT: dict[PresentationLanguage, dict[str, tuple[str, str]]] = {
    "en": {
        "activity_eval_insufficient_title": (
            "Limited training-effect data",
            "The activity does not contain enough Training Effect data for a useful pass classification.",
        ),
        "activity_eval_mixed_title": (
            "Mixed aerobic and anaerobic session",
            "The session produced meaningful aerobic and anaerobic training stimulus.",
        ),
        "activity_eval_anaerobic_title": (
            "Anaerobic-focused session",
            "The session was dominated by anaerobic training effect.",
        ),
        "activity_eval_aerobic_development_title": (
            "Strong aerobic session",
            "The session produced a clear aerobic development stimulus.",
        ),
        "activity_eval_short_aerobic_title": (
            "Short aerobic session",
            "The session produced mainly aerobic training effect with little anaerobic impact.",
        ),
        "activity_eval_aerobic_title": (
            "Aerobic session",
            "The session produced mainly aerobic training effect.",
        ),
        "activity_eval_recovery_title": (
            "Very light session",
            "The measured training effect was low and resembles recovery or easy activity.",
        ),
        "activity_eval_light_title": (
            "Light training session",
            "The activity produced a limited but measurable training stimulus.",
        ),
    },
    "sv": {
        "activity_eval_insufficient_title": (
            "Begränsat underlag",
            "Passet saknar tillräcklig Training Effect-data för en meningsfull klassificering.",
        ),
        "activity_eval_mixed_title": (
            "Blandat aerobt och anaerobt pass",
            "Passet gav tydlig både aerob och anaerob träningseffekt.",
        ),
        "activity_eval_anaerobic_title": (
            "Anaerobt inriktat pass",
            "Passet dominerades av anaerob träningseffekt.",
        ),
        "activity_eval_aerobic_development_title": (
            "Tydligt aerobt utvecklingspass",
            "Passet gav en tydlig aerob utvecklingsstimulus.",
        ),
        "activity_eval_short_aerobic_title": (
            "Kort aerobt pass",
            "Passet gav framför allt aerob träningseffekt med liten anaerob påverkan.",
        ),
        "activity_eval_aerobic_title": (
            "Aerobt pass",
            "Passet gav framför allt aerob träningseffekt.",
        ),
        "activity_eval_recovery_title": (
            "Mycket lätt pass",
            "Den uppmätta träningseffekten var låg och liknar återhämtning eller lätt aktivitet.",
        ),
        "activity_eval_light_title": (
            "Lätt träningspass",
            "Passet gav en begränsad men mätbar träningseffekt.",
        ),
    },
}

_ACTIVITY_NAMES: dict[PresentationLanguage, dict[str, str]] = {
    "en": {
        "virtual_ride": "Virtual cycling",
        "cycling": "Cycling",
        "road_biking": "Cycling",
        "indoor_cycling": "Indoor cycling",
        "mountain_biking": "Mountain biking",
        "gravel_cycling": "Gravel cycling",
        "rowing_v2": "Rowing",
        "rowing": "Rowing",
        "running": "Running",
        "trail_running": "Trail running",
        "treadmill_running": "Treadmill",
        "walking": "Walking",
        "hiking": "Hiking",
        "strength_training": "Strength training",
        "strength": "Strength training",
        "swimming": "Swimming",
        "lap_swimming": "Pool swimming",
        "open_water_swimming": "Open-water swimming",
        "yoga": "Yoga",
    },
    "sv": {
        "virtual_ride": "Inomhuscykling",
        "cycling": "Cykling",
        "road_biking": "Cykling",
        "indoor_cycling": "Inomhuscykling",
        "mountain_biking": "Mountainbike",
        "gravel_cycling": "Gravelcykling",
        "rowing_v2": "Rodd",
        "rowing": "Rodd",
        "running": "Löpning",
        "trail_running": "Traillöpning",
        "treadmill_running": "Löpband",
        "walking": "Promenad",
        "hiking": "Vandring",
        "strength_training": "Styrketräning",
        "strength": "Styrketräning",
        "swimming": "Simning",
        "lap_swimming": "Bassängsimning",
        "open_water_swimming": "Öppet vatten",
        "yoga": "Yoga",
    },
}

_ACTIVITY_ICONS = {
    "virtual_ride": "mdi:bike",
    "cycling": "mdi:bike",
    "road_biking": "mdi:bike",
    "indoor_cycling": "mdi:bike",
    "mountain_biking": "mdi:bike",
    "gravel_cycling": "mdi:bike",
    "rowing_v2": "mdi:rowing",
    "rowing": "mdi:rowing",
    "running": "mdi:run",
    "trail_running": "mdi:run",
    "treadmill_running": "mdi:run",
    "walking": "mdi:walk",
    "hiking": "mdi:walk",
    "strength_training": "mdi:dumbbell",
    "strength": "mdi:dumbbell",
    "swimming": "mdi:swim",
    "lap_swimming": "mdi:swim",
    "open_water_swimming": "mdi:swim",
    "yoga": "mdi:meditation",
}

_CONFIDENCE: dict[PresentationLanguage, dict[str, str]] = {
    "en": {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "unavailable": "Unavailable",
    },
    "sv": {
        "high": "Hög",
        "medium": "Medel",
        "low": "Låg",
        "unavailable": "Saknas",
    },
}

_MONTHS_SV = ("jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def normalize_activity_evaluation_language(language: str | None) -> PresentationLanguage:
    """Return a supported activity-evaluation presentation language."""
    if isinstance(language, str) and language.lower().startswith("sv"):
        return "sv"
    return "en"


def activity_name(activity_type: str | None, language: str | None) -> str:
    """Return a localized activity name while keeping unknown types visible."""
    selected = normalize_activity_evaluation_language(language)
    machine_type = activity_type or "unknown"
    return _ACTIVITY_NAMES[selected].get(machine_type, machine_type.replace("_", " ").title())


def activity_icon(activity_type: str | None) -> str:
    """Return an icon for a normalized activity type."""
    return _ACTIVITY_ICONS.get(activity_type or "", "mdi:run-fast")


def present_activity_evaluation(
    evaluation: Mapping[str, Any], language: str | None
) -> dict[str, Any]:
    """Add localized presentation without changing evaluation semantics."""
    selected = normalize_activity_evaluation_language(language)
    title_key = str(evaluation.get("title_key") or "activity_eval_insufficient_title")
    title, message = _ASSESSMENT_TEXT[selected].get(
        title_key,
        (title_key.replace("_", " ").title(), ""),
    )
    activity_type = str(evaluation.get("activity_type") or "unknown")
    confidence = str(evaluation.get("performance_confidence") or "unavailable")
    return {
        **dict(evaluation),
        "activity_name": activity_name(activity_type, selected),
        "activity_icon": activity_icon(activity_type),
        "title": title,
        "message": message,
        "confidence_label": _CONFIDENCE[selected].get(confidence, confidence),
        "presentation_language": selected,
    }


def activity_option_label(
    evaluation: Mapping[str, Any],
    language: str | None,
    *,
    today: date,
) -> str:
    """Return a compact localized option label for the recent-pass selector."""
    selected = normalize_activity_evaluation_language(language)
    raw_date = evaluation.get("calendar_date")
    activity_date: date | None = None
    if isinstance(raw_date, str):
        try:
            activity_date = date.fromisoformat(raw_date)
        except ValueError:
            activity_date = None

    if activity_date == today:
        date_label = "Idag" if selected == "sv" else "Today"
    elif activity_date is not None:
        months = _MONTHS_SV if selected == "sv" else _MONTHS_EN
        date_label = (
            f"{activity_date.day} {months[activity_date.month - 1]}"
            if selected == "sv"
            else f"{months[activity_date.month - 1]} {activity_date.day}"
        )
    else:
        date_label = str(raw_date or "—")

    duration = evaluation.get("duration_minutes")
    duration_label = (
        f"{round(float(duration))} min" if isinstance(duration, (int, float)) else "—"
    )
    return f"{date_label} · {activity_name(str(evaluation.get('activity_type') or 'unknown'), selected)} · {duration_label}"
