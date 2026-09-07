"""Sensor entity for deterministic Garmin Insights V1."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .insights_coordinator import InsightsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_add_insights_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: InsightsCoordinator,
) -> None:
    """Add the Insights overview entity to the loaded sensor platform."""
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
            "Garmin Insights entity was not added because the sensor platform "
            "was not available for config entry %s",
            entry.entry_id,
        )
        return

    await sensor_platform.async_add_entities(
        [GarminInsightsOverviewSensor(coordinator, entry.entry_id)]
    )


class GarminInsightsOverviewSensor(CoordinatorEntity[InsightsCoordinator], SensorEntity):
    """Expose one stable presentation-ready Garmin Insights overview."""

    _attr_has_entity_name = True
    _attr_name = "Overview"
    _attr_icon = "mdi:lightbulb-on-outline"

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

    @property
    def native_value(self) -> str | None:
        """Return the current overall Insights status."""
        if not self.coordinator.data:
            return None
        return cast(str | None, self.coordinator.data.get("status"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose stable rule results and their input provenance."""
        data = self.coordinator.data or {}
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
            "results": data.get("results") or [],
            "data_quality": data.get("data_quality"),
            "recovery": data.get("recovery"),
            "training": data.get("training"),
            "load_focus": data.get("load_focus"),
            "recent_activity_count": data.get("recent_activity_count", 0),
            "recent_activities": data.get("recent_activities") or [],
        }
