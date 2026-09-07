"""Tests for the Home Assistant Garmin Insights presentation adapter."""

from custom_components.garmin_connect.insights_presentation import (
    normalize_insights_language,
    present_insight_result,
    status_presentation,
)


def test_normalize_insights_language_supports_swedish_and_english_fallback() -> None:
    assert normalize_insights_language("sv-SE") == "sv"
    assert normalize_insights_language("sv") == "sv"
    assert normalize_insights_language("en-GB") == "en"
    assert normalize_insights_language("de-DE") == "en"
    assert normalize_insights_language(None) == "en"


def test_present_low_recent_load_in_swedish() -> None:
    presented = present_insight_result(
        {
            "id": "low_recent_load",
            "severity": "info",
            "priority": 45,
            "confidence": "medium",
            "ruleset_version": 1,
            "evidence": [
                {
                    "code": "acwr_below_low_load_threshold",
                    "value": 0.212,
                    "threshold": 0.5,
                },
                {
                    "code": "negative_ramp_rate",
                    "value": -3.326,
                    "threshold": None,
                },
            ],
        },
        "sv-SE",
    )

    assert presented["title"] == "Träningsbelastningen har minskat"
    assert presented["icon"] == "mdi:trending-down"
    assert presented["evidence"][0]["label"] == (
        "ACWR under gränsen för låg belastning"
    )
    assert presented["evidence"][1]["label"] == "Negativ Ramp Rate"


def test_present_morning_readiness_keeps_source_visible() -> None:
    presented = present_insight_result(
        {
            "id": "favourable_training_signal",
            "severity": "positive",
            "priority": 30,
            "confidence": "high",
            "ruleset_version": 1,
            "evidence": [
                {
                    "code": "morning_training_readiness_good",
                    "value": 92.0,
                    "threshold": 70.0,
                }
            ],
        },
        "sv",
    )

    assert presented["title"] == "Goda återhämtningssignaler"
    assert presented["evidence"][0] == {
        "code": "morning_training_readiness_good",
        "label": "Morgonens Training Readiness",
        "value": 92.0,
        "threshold": 70.0,
    }


def test_dynamic_data_quality_evidence_is_human_readable() -> None:
    presented = present_insight_result(
        {
            "id": "insufficient_or_stale_data",
            "evidence": [
                {"code": "missing_source.hrv", "value": None, "threshold": None},
                {
                    "code": "missing_field.recovery.sleep_score",
                    "value": None,
                    "threshold": None,
                },
            ],
        },
        "sv",
    )

    assert presented["evidence"][0]["label"] == "Datakälla saknas: hrv"
    assert presented["evidence"][1]["label"] == (
        "Datafält saknas: recovery.sleep score"
    )


def test_status_presentation_keeps_machine_status_separate() -> None:
    assert status_presentation("warning", "sv") == {
        "label": "Varning",
        "icon": "mdi:alert-circle-outline",
    }
    assert status_presentation("positive", "en") == {
        "label": "Positive",
        "icon": "mdi:check-circle-outline",
    }
