"""Sensor entity for the selected Garmin activity evaluation."""

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

from .activity_evaluation_coordinator import ActivityEvaluationCoordinator
from .activity_evaluation_presentation import (
    normalize_activity_evaluation_language,
    present_activity_evaluation,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_add_activity_evaluation_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ActivityEvaluationCoordinator,
) -> None:
    """Add the selected activity-evaluation sensor to the loaded sensor platform."""
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
            "Garmin Activity Evaluation sensor was not added because the sensor "
            "platform was unavailable for config entry %s",
            entry.entry_id,
        )
        return

    await sensor_platform.async_add_entities(
        [GarminActivityEvaluationSensor(coordinator, entry.entry_id)]
    )


class GarminActivityEvaluationSensor(
    CoordinatorEntity[ActivityEvaluationCoordinator], SensorEntity
):
    """Expose the currently selected recent pass evaluation."""

    _attr_has_entity_name = False
    _attr_name = "Garmin Activity Evaluation"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"

    def __init__(
        self,
        coordinator: ActivityEvaluationCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the selected-pass evaluation sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_activity_evaluation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_activity_evaluation")},
            name="Garmin Activity Evaluation",
            manufacturer="Garmin",
            model="Recent activity evaluation",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _presentation_language(self) -> str:
        """Return the current HA language in the supported presentation set."""
        config = getattr(self.coordinator.hass, "config", None)
        language = getattr(config, "language", None)
        return normalize_activity_evaluation_language(
            language if isinstance(language, str) else None
        )

    @property
    def available(self) -> bool:
        """Return whether at least one recent evaluation is ready."""
        return (
            super().available
            and bool(self.coordinator.data)
            and bool(self.coordinator.data.get("ready"))
            and self.coordinator.data.get("selected_evaluation") is not None
        )

    @property
    def native_value(self) -> str | None:
        """Return the stable machine assessment ID for the selected activity."""
        data = self.coordinator.data or {}
        selected = data.get("selected_evaluation")
        if not isinstance(selected, dict):
            return None
        return cast(str | None, selected.get("assessment_id"))

    @property
    def icon(self) -> str:
        """Return an activity-specific icon."""
        attrs = self.extra_state_attributes
        value = attrs.get("activity_icon")
        return str(value) if value else "mdi:chart-timeline-variant-shimmer"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the selected raw evaluation plus localized presentation."""
        data = self.coordinator.data or {}
        selected = data.get("selected_evaluation")
        if not isinstance(selected, dict):
            return {
                "status": data.get("status"),
                "evaluation_count": data.get("evaluation_count", 0),
                "selected_activity_id": data.get("selected_activity_id"),
            }

        presented = present_activity_evaluation(
            selected,
            self._presentation_language(),
        )
        return {
            **presented,
            "status": data.get("status"),
            "evaluation_count": data.get("evaluation_count", 0),
            "selected_activity_id": data.get("selected_activity_id"),
            "body_weight_kg": data.get("body_weight_kg"),
            "user_max_hr": data.get("max_hr"),
            "evaluation_limit": data.get("limit"),
        }
