"""Sensor entities for deterministic Garmin Insights and daily load budget."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .insights_coordinator import InsightsCoordinator
from .insights_presentation import (
    normalize_insights_language,
    present_insight_results,
    status_presentation,
)

_LOGGER = logging.getLogger(__name__)

_BUDGET_FACTOR_LABELS = {
    "en": {
        "acwr": "ACWR",
        "strain": "Strain",
        "tsb": "Form balance (TSB)",
        "ramp_rate": "Ramp Rate",
        "recovery_caution": "Recovery signals",
        "insufficient_or_stale_data": "Limited current data",
    },
    "sv": {
        "acwr": "ACWR",
        "strain": "Strain",
        "tsb": "Formbalans (TSB)",
        "ramp_rate": "Ramp Rate",
        "recovery_caution": "Återhämtningssignaler",
        "insufficient_or_stale_data": "Begränsat aktuellt underlag",
    },
}


async def async_add_insights_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: InsightsCoordinator,
) -> None:
    """Add the Insights overview and daily load budget entities."""
    sensor_platform = next(
        (
            platform
            for platform in async_get_platforms(hass, DOMAIN)
            if platform.domain == Platform.SENSOR
            and platform.config_entry is not None
            and platform.config_entry.entry_id == entry.entry_id
        ),
        None,
    )
    if sensor_platform is None:
        _LOGGER.warning(
            "Garmin Insights entities were not added because the sensor platform "
            "was not available for config entry %s",
            entry.entry_id,
        )
        return

    await sensor_platform.async_add_entities(
        [
            GarminInsightsOverviewSensor(coordinator, entry.entry_id),
            GarminDailyLoadBudgetSensor(coordinator, entry.entry_id),
        ]
    )


class GarminInsightsOverviewSensor(CoordinatorEntity[InsightsCoordinator], SensorEntity):
    """Expose one stable presentation-ready Garmin Insights overview."""

    _attr_has_entity_name = True
    _attr_name = "Overview"

    def __init__(
        self,
        coordinator: InsightsCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the Garmin Insights overview sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_insights_overview"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_insights")},
            name="Garmin Insights",
            manufacturer="Garmin",
            model="Deterministic Insights V1",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _presentation_language(self) -> str:
        """Return the configured HA language in the supported presentation set."""
        config = getattr(self.coordinator.hass, "config", None)
        language = getattr(config, "language", None)
        return normalize_insights_language(language if isinstance(language, str) else None)

    @property
    def native_value(self) -> str | None:
        """Return the current overall Insights status."""
        if not self.coordinator.data:
            return None
        return cast(str | None, self.coordinator.data.get("status"))

    @property
    def icon(self) -> str:
        """Return an icon matching the stable machine status."""
        data = self.coordinator.data or {}
        status = cast(str | None, data.get("status"))
        return status_presentation(status, self._presentation_language())["icon"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose stable raw results plus a localized HA presentation layer."""
        data = self.coordinator.data or {}
        language = self._presentation_language()
        raw_results = data.get("results") or []
        presented_results = present_insight_results(raw_results, language)
        primary = presented_results[0] if presented_results else None
        status = cast(str | None, data.get("status"))
        presented_status = status_presentation(status, language)

        return {
            "configured": data.get("configured", False),
            "snapshot_complete": data.get("snapshot_complete", False),
            "as_of": data.get("as_of"),
            "snapshot_date": data.get("snapshot_date"),
            "ruleset_version": data.get("ruleset_version"),
            "result_count": data.get("result_count", 0),
            "result_ids": data.get("result_ids") or [],
            "primary_result_id": data.get("primary_result_id"),
            "primary_severity": data.get("primary_severity"),
            "primary_confidence": data.get("primary_confidence"),
            "results": raw_results,
            "presentation_language": language,
            "status_label": presented_status["label"],
            "status_icon": presented_status["icon"],
            "primary_title": primary.get("title") if primary else None,
            "primary_message": primary.get("message") if primary else None,
            "primary_icon": primary.get("icon") if primary else None,
            "presented_results": presented_results,
            "data_quality": data.get("data_quality"),
            "recovery": data.get("recovery"),
            "training": data.get("training"),
            "load_focus": data.get("load_focus"),
            "recent_activity_count": data.get("recent_activity_count", 0),
            "recent_activities": data.get("recent_activities") or [],
            "daily_load_budget": data.get("daily_load_budget"),
        }


class GarminDailyLoadBudgetSensor(CoordinatorEntity[InsightsCoordinator], SensorEntity):
    """Expose the remaining conservative training-load budget for today."""

    _attr_has_entity_name = False
    _attr_name = "Garmin Daily Load Budget"
    _attr_native_unit_of_measurement = "TRIMP"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:gauge"

    def __init__(
        self,
        coordinator: InsightsCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the Garmin daily load budget sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_fitness_daily_load_budget"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_fitness")},
            name="Garmin Fitness",
            manufacturer="Garmin",
            model="Fitness analytics",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return whether a current budget recommendation is available."""
        return super().available and isinstance(
            (self.coordinator.data or {}).get("daily_load_budget"),
            dict,
        )

    @property
    def native_value(self) -> float | None:
        """Return remaining recommended TRIMP for today."""
        budget = (self.coordinator.data or {}).get("daily_load_budget")
        if not isinstance(budget, dict):
            return None
        value = budget.get("remaining_load")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose recommendation, projections and transparent policy limits."""
        budget = (self.coordinator.data or {}).get("daily_load_budget")
        if not isinstance(budget, dict):
            return {}

        config = getattr(self.coordinator.hass, "config", None)
        language = getattr(config, "language", None)
        selected_language = normalize_insights_language(
            language if isinstance(language, str) else None
        )
        factor = str(budget.get("limiting_factor") or "")
        structural_factor = str(budget.get("structural_limiting_factor") or "")
        labels = _BUDGET_FACTOR_LABELS[selected_language]

        return {
            **budget,
            "presentation_language": selected_language,
            "limiting_factor_label": labels.get(factor, factor),
            "structural_limiting_factor_label": labels.get(
                structural_factor,
                structural_factor,
            ),
            "advisory": True,
        }
