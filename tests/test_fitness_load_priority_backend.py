"""Tests for the opt-in Load Priority backend and HA service."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from ha_garmin.fitness.models import ActivityMetrics
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from custom_components.garmin_connect.const import DOMAIN, FITNESS_DATA_KEY
from custom_components.garmin_connect.fitness_load_priority_backend import (
    build_load_priority_report,
)
from custom_components.garmin_connect.fitness_service import (
    SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW,
    async_setup_fitness_probe_service,
    async_unload_fitness_probe_service,
)


def _activity(activity_id: int, sport: str, **changes: object) -> ActivityMetrics:
    values = {
        "activity_id": activity_id,
        "calendar_date": date(2026, 9, 15),
        "start_time": datetime(2026, 9, 15, 8, tzinfo=UTC),
        "activity_type": sport,
        "duration_minutes": 30.0,
        "distance_meters": 3000.0,
        "avg_hr": 105.0,
        "max_hr": 125.0,
        "calories": None,
        "aerobic_training_effect": None,
        "anaerobic_training_effect": None,
        "garmin_training_load": 14.4,
        "vo2max": None,
        "avg_power": None,
        "normalized_power": None,
    }
    values.update(changes)
    return ActivityMetrics(**values)


def _context(*activities: ActivityMetrics):
    return SimpleNamespace(
        activities=activities,
        resting_hr_by_date={date(2026, 9, 15): 48.0},
    )


def test_walking_uses_hr_without_changing_existing_history() -> None:
    context = _context(_activity(1, "walking"))
    before = tuple(context.activities)
    result = build_load_priority_report(context, user_max_hr=185, sex="male")
    item = result["activities"][0]
    assert item["selected_source"] == "hr"
    assert item["unit"] == "banister_trimp"
    assert item["load"] != 14.4
    assert item["canonical_compatible"] is False
    assert result["budget_modified"] is False
    assert result["mixed_units_must_not_be_summed"] is True
    assert context.activities == before


def test_cycling_power_then_hr_fallback() -> None:
    activity = _activity(2, "virtual_ride", normalized_power=180.0)
    powered = build_load_priority_report(
        _context(activity), user_max_hr=185, sex="male", ftp_watts=200
    )["activities"][0]
    assert powered["selected_source"] == "power"
    assert powered["load"] == 40.5
    assert powered["unit"] == "power_tss"
    fallback = build_load_priority_report(
        _context(activity), user_max_hr=185, sex="male"
    )["activities"][0]
    assert fallback["selected_source"] == "hr"
    assert fallback["attempts"][0]["reason"] == "missing_or_invalid_ftp"


def test_manual_override_does_not_fallback_or_turn_missing_into_zero() -> None:
    result = build_load_priority_report(
        _context(_activity(3, "walking", avg_hr=None)),
        user_max_hr=185,
        sex="male",
        sport="walking",
        override="hr",
    )
    item = result["activities"][0]
    assert item["selected_source"] is None
    assert item["load"] is None
    assert result["unavailable_in_returned"] == 1


def test_sport_filter_and_priority_do_not_change_other_activities() -> None:
    result = build_load_priority_report(
        _context(_activity(1, "walking"), _activity(2, "virtual_ride")),
        user_max_hr=185,
        sex="male",
        sport="walking",
        priority=["garmin", "hr"],
    )
    assert result["matched_activities"] == 1
    assert result["activities"][0]["selected_source"] == "garmin"
    assert result["activities"][0]["unit"] == "garmin_training_load"
    with pytest.raises(ValueError, match="sport is required"):
        build_load_priority_report(
            _context(_activity(1, "walking")),
            user_max_hr=185,
            sex="male",
            priority=["hr"],
        )


async def test_service_uses_matching_account_and_cached_context() -> None:
    hass = MagicMock()
    hass.services.has_service.return_value = False
    client = object()
    fitness = SimpleNamespace(
        client=client,
        configured=True,
        insight_context=_context(_activity(4, "walking")),
        user_max_hr=185.0,
        sex="male",
    )
    hass.data = {FITNESS_DATA_KEY: {"entry1": fitness}}
    with patch(
        "custom_components.garmin_connect.fitness_service._get_client",
        return_value=client,
    ):
        await async_setup_fitness_probe_service(hass)
        calls = hass.services.async_register.call_args_list
        registered = [
            call for call in calls
            if call.args[1] == SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW
        ]
        assert len(registered) == 1
        assert registered[0].kwargs["supports_response"] is SupportsResponse.ONLY
        service_call = SimpleNamespace(data={"limit": 3, "sport": "walking"})
        result = await registered[0].args[2](service_call)
        assert result["activities"][0]["selected_source"] == "hr"

    # A different account must NEVER silently reuse this account's HR context.
    with patch(
        "custom_components.garmin_connect.fitness_service._get_client",
        return_value=object(),
    ):
        with pytest.raises(HomeAssistantError, match="not ready for this account"):
            await registered[0].args[2](service_call)

    hass.services.has_service.return_value = True
    await async_unload_fitness_probe_service(hass)
    assert hass.services.async_remove.call_count == 2
    assert any(
        item.args == (DOMAIN, SERVICE_FITNESS_LOAD_PRIORITY_PREVIEW)
        for item in hass.services.async_remove.call_args_list
    )
