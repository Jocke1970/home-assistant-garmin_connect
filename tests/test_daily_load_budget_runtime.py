"""Tests for the Home Assistant daily training-load budget entity."""

from unittest.mock import MagicMock

from custom_components.garmin_connect.insights_sensor import GarminDailyLoadBudgetSensor


def test_daily_load_budget_sensor_exposes_recommendation_and_policy() -> None:
    coordinator = MagicMock()
    coordinator.hass.config.language = "sv-SE"
    coordinator.last_update_success = True
    coordinator.data = {
        "daily_load_budget": {
            "date": "2026-09-08",
            "policy_version": 1,
            "current_load": 31.0,
            "structural_max_load": 72.2,
            "structural_remaining_load": 41.2,
            "recommended_max_load": 72.2,
            "remaining_load": 41.2,
            "structural_limiting_factor": "acwr",
            "limiting_factor": "acwr",
            "recovery_modifier": 1.0,
            "recovery_modifier_reason": "none",
            "projected_acwr": 1.29,
            "projected_strain": 12.8,
            "projected_tsb": -7.2,
            "projected_ramp_rate": 3.1,
            "acwr_limit": 1.3,
            "strain_limit": 14.0,
            "tsb_floor": -10.0,
            "ramp_rate_limit": 5.0,
            "acwr_max_load": 72.2,
            "strain_max_load": 110.0,
            "tsb_max_load": 83.0,
            "ramp_rate_max_load": 95.0,
        }
    }

    sensor = GarminDailyLoadBudgetSensor(coordinator, "entry_1")

    assert sensor.native_value == 41.2
    assert sensor.native_unit_of_measurement == "TRIMP"
    assert sensor.icon == "mdi:gauge"
    attrs = sensor.extra_state_attributes
    assert attrs["recommended_max_load"] == 72.2
    assert attrs["current_load"] == 31.0
    assert attrs["projected_acwr"] == 1.29
    assert attrs["limiting_factor_label"] == "ACWR"
    assert attrs["structural_limiting_factor_label"] == "ACWR"
    assert attrs["presentation_language"] == "sv"
    assert attrs["advisory"] is True


def test_daily_load_budget_sensor_localizes_recovery_limit() -> None:
    coordinator = MagicMock()
    coordinator.hass.config.language = "sv-SE"
    coordinator.last_update_success = True
    coordinator.data = {
        "daily_load_budget": {
            "remaining_load": 18.0,
            "limiting_factor": "recovery_caution",
            "structural_limiting_factor": "tsb",
        }
    }

    sensor = GarminDailyLoadBudgetSensor(coordinator, "entry_1")
    attrs = sensor.extra_state_attributes

    assert attrs["limiting_factor_label"] == "Återhämtningssignaler"
    assert attrs["structural_limiting_factor_label"] == "Formbalans (TSB)"
