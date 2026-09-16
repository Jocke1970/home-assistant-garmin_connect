"""Home Assistant presentation helpers for Garmin Insights V1.

This module intentionally owns only user-facing labels, messages and icons.
Deterministic rule semantics remain in ha-garmin and are consumed through the
stable rule/result contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

PresentationLanguage = Literal["en", "sv"]

_RESULT_TEXT: dict[PresentationLanguage, dict[str, tuple[str, str]]] = {
    "en": {
        "insufficient_or_stale_data": (
            "Some insight data is incomplete",
            "Some inputs are missing or not current. Other insights are shown only when their own data requirements are met.",
        ),
        "load_spike": (
            "Training load has increased quickly",
            "Your recent load is high relative to your established training level.",
        ),
        "recovery_caution": (
            "Recovery signals are limited",
            "Several current recovery signals point in a more cautious direction.",
        ),
        "low_recent_load": (
            "Training load has decreased",
            "Your recent load is clearly below your established training level.",
        ),
        "load_focus_imbalance": (
            "Training focus is one-sided",
            "Recent Training Effect is strongly concentrated in one load-focus category.",
        ),
        "favourable_training_signal": (
            "Favourable recovery signals",
            "Several current recovery values look favourable together.",
        ),
    },
    "sv": {
        "insufficient_or_stale_data": (
            "Vissa insiktsdata är ofullständiga",
            "Vissa underlag saknas eller är inte aktuella. Övriga insikter visas bara när deras egna datakrav är uppfyllda.",
        ),
        "load_spike": (
            "Träningsbelastningen har ökat snabbt",
            "Din senaste belastning ligger högt i förhållande till din etablerade träningsnivå.",
        ),
        "recovery_caution": (
            "Återhämtningssignalerna är begränsade",
            "Flera aktuella återhämtningssignaler pekar åt ett försiktigare håll.",
        ),
        "low_recent_load": (
            "Träningsbelastningen har minskat",
            "Din senaste belastning ligger tydligt under din etablerade träningsnivå.",
        ),
        "load_focus_imbalance": (
            "Träningsfokuset är ensidigt",
            "Den senaste tidens Training Effect är tydligt koncentrerad till en belastningstyp.",
        ),
        "favourable_training_signal": (
            "Goda återhämtningssignaler",
            "Flera aktuella återhämtningsvärden verkar gynnsamma tillsammans.",
        ),
    },
}

_RESULT_ICONS = {
    "insufficient_or_stale_data": "mdi:database-alert-outline",
    "load_spike": "mdi:trending-up",
    "recovery_caution": "mdi:heart-pulse",
    "low_recent_load": "mdi:trending-down",
    "load_focus_imbalance": "mdi:chart-donut",
    "favourable_training_signal": "mdi:check-circle-outline",
}

_STATUS_TEXT: dict[PresentationLanguage, dict[str, str]] = {
    "en": {
        "clear": "No active insights",
        "positive": "Positive",
        "info": "Information",
        "caution": "Caution",
        "warning": "Warning",
        "waiting_for_fitness": "Waiting for Fitness data",
        "unconfigured": "Not configured",
    },
    "sv": {
        "clear": "Inga aktiva insikter",
        "positive": "Gynnsam",
        "info": "Information",
        "caution": "Observera",
        "warning": "Varningsläge",
        "waiting_for_fitness": "Väntar på Fitness-data",
        "unconfigured": "Inte konfigurerad",
    },
}

_STATUS_ICONS = {
    "clear": "mdi:check-circle-outline",
    "positive": "mdi:check-circle-outline",
    "info": "mdi:information-outline",
    "caution": "mdi:alert-outline",
    "warning": "mdi:alert-circle-outline",
    "waiting_for_fitness": "mdi:timer-sand",
    "unconfigured": "mdi:cog-outline",
}

_EVIDENCE_TEXT: dict[PresentationLanguage, dict[str, str]] = {
    "en": {
        "snapshot_incomplete": "Snapshot incomplete",
        "acwr_above_spike_threshold": "ACWR above load-spike threshold",
        "positive_ramp_rate": "Positive Ramp Rate",
        "atl_above_ctl": "ATL above CTL",
        "acwr_below_low_load_threshold": "ACWR below low-load threshold",
        "negative_ramp_rate": "Negative Ramp Rate",
        "sparse_recent_activity_window": "Few recent activities",
        "training_readiness_low": "Training Readiness low",
        "morning_training_readiness_low": "Morning Training Readiness low",
        "sleep_score_low": "Sleep Score low",
        "body_battery_low": "Body Battery low",
        "average_stress_high": "Average stress high",
        "recovery_time_long": "Recovery Time long",
        "resting_hr_elevated": "Resting heart rate elevated",
        "hrv_below_balanced_baseline": "HRV below balanced baseline",
        "hrv_status_unfavourable": "HRV status unfavourable",
        "training_readiness_good": "Training Readiness",
        "morning_training_readiness_good": "Morning Training Readiness",
        "sleep_score_good": "Sleep Score",
        "hrv_balanced": "HRV balanced",
        "hrv_within_balanced_baseline": "HRV within balanced baseline",
        "body_battery_good": "Body Battery",
        "resting_hr_near_or_below_baseline": "Resting heart rate near or below baseline",
        "recent_focus_activity_count": "Activities with Training Effect",
        "dominance_ratio": "Load-focus dominance ratio",
        "exclusive_recent_focus": "Only one load-focus category represented",
    },
    "sv": {
        "snapshot_incomplete": "Ofullständig snapshot",
        "acwr_above_spike_threshold": "ACWR över gränsen för belastningsökning",
        "positive_ramp_rate": "Ramp Rate över noll",
        "atl_above_ctl": "ATL över CTL",
        "acwr_below_low_load_threshold": "ACWR under gränsen för låg belastning",
        "negative_ramp_rate": "Ramp Rate under noll",
        "sparse_recent_activity_window": "Få aktiviteter den senaste tiden",
        "training_readiness_low": "Training Readiness låg",
        "morning_training_readiness_low": "Morgonens Training Readiness låg",
        "sleep_score_low": "Sömnpoäng låg",
        "body_battery_low": "Body Battery låg",
        "average_stress_high": "Genomsnittlig stress hög",
        "recovery_time_long": "Lång återhämtningstid",
        "resting_hr_elevated": "Förhöjd vilopuls",
        "hrv_below_balanced_baseline": "HRV under balanserad baslinje",
        "hrv_status_unfavourable": "HRV-status ogynnsam",
        "training_readiness_good": "Training Readiness",
        "morning_training_readiness_good": "Morgonens Training Readiness",
        "sleep_score_good": "Sömnpoäng",
        "hrv_balanced": "HRV balanserad",
        "hrv_within_balanced_baseline": "HRV inom balanserad baslinje",
        "body_battery_good": "Body Battery",
        "resting_hr_near_or_below_baseline": "Vilopuls nära eller under baslinje",
        "recent_focus_activity_count": "Aktiviteter med Training Effect",
        "dominance_ratio": "Dominanskvot för träningsfokus",
        "exclusive_recent_focus": "Endast en belastningstyp representerad",
    },
}

_DYNAMIC_PREFIX_TEXT: dict[PresentationLanguage, dict[str, str]] = {
    "en": {
        "missing_source.": "Missing source",
        "missing_field.": "Missing field",
        "stale.": "Stale input",
        "dominant_focus.": "Dominant load focus",
    },
    "sv": {
        "missing_source.": "Datakälla saknas",
        "missing_field.": "Datafält saknas",
        "stale.": "Inaktuellt underlag",
        "dominant_focus.": "Dominerande träningsfokus",
    },
}


def normalize_insights_language(language: str | None) -> PresentationLanguage:
    """Return a supported presentation language, defaulting to English."""
    if isinstance(language, str) and language.lower().startswith("sv"):
        return "sv"
    return "en"


def status_presentation(status: str | None, language: str | None) -> dict[str, str]:
    """Present the stable machine status without changing its semantics."""
    selected = normalize_insights_language(language)
    machine_status = status or "clear"
    return {
        "label": _STATUS_TEXT[selected].get(machine_status, machine_status),
        "icon": _STATUS_ICONS.get(machine_status, "mdi:lightbulb-on-outline"),
    }


def _evidence_label(code: str, language: PresentationLanguage) -> str:
    """Translate one evidence code while preserving unknown codes visibly."""
    direct = _EVIDENCE_TEXT[language].get(code)
    if direct is not None:
        return direct

    for prefix, label in _DYNAMIC_PREFIX_TEXT[language].items():
        if code.startswith(prefix):
            suffix = code.removeprefix(prefix).replace("_", " ")
            return f"{label}: {suffix}"

    return code.replace("_", " ")


def present_insight_result(
    result: Mapping[str, Any], language: str | None
) -> dict[str, Any]:
    """Convert one machine-readable result into HA-facing presentation data."""
    selected = normalize_insights_language(language)
    result_id = str(result.get("id") or "unknown")
    title, message = _RESULT_TEXT[selected].get(
        result_id,
        (result_id.replace("_", " ").title(), ""),
    )

    raw_evidence = result.get("evidence")
    evidence_items = raw_evidence if isinstance(raw_evidence, list) else []
    evidence = []
    for item in evidence_items:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "unknown")
        evidence.append(
            {
                "code": code,
                "label": _evidence_label(code, selected),
                "value": item.get("value"),
                "threshold": item.get("threshold"),
            }
        )

    return {
        "id": result_id,
        "severity": result.get("severity"),
        "priority": result.get("priority"),
        "confidence": result.get("confidence"),
        "title": title,
        "message": message,
        "icon": _RESULT_ICONS.get(result_id, "mdi:lightbulb-on-outline"),
        "evidence": evidence,
        "ruleset_version": result.get("ruleset_version"),
    }


def present_insight_results(
    results: Iterable[Mapping[str, Any]], language: str | None
) -> list[dict[str, Any]]:
    """Present all deterministic results in their existing priority order."""
    return [present_insight_result(result, language) for result in results]
