"""Sensor entities for Garmin Fitness analytics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .fitness_coordinator import FitnessCoordinator

_LOGGER = logging.getLogger(__name__)
FITNESS_UNIT = "TRIMP"


@dataclass(frozen=True, kw_only=True)
class GarminFitnessSensorEntityDescription(SensorEntityDescription):
    """Describe one Garmin Fitness sensor."""


FITNESS_SENSOR_DESCRIPTIONS: tuple[GarminFitnessSensorEntityDescription, ...] = (
    GarminFitnessSensorEntityDescription(
        key="daily_load",
        name="Daily load",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=FITNESS_UNIT,
        suggested_display_precision=1,
    ),
    GarminFitnessSensorEntityDescription(
        key="ctl",
        name="CTL",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=FITNESS_UNIT,
        suggested_display_precision=1,
    ),
    GarminFitnessSensorEntityDescription(
        key="atl",
        name="ATL",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=FITNESS_UNIT,
        suggested_display_precision=1,
    ),
    GarminFitnessSensorEntityDescription(
        key="tsb",
        name="TSB",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=FITNESS_UNIT,
        suggested_display_precision=1,
    ),
)


async def async_add_fitness_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: FitnessCoordinator,
) -> None:
    """Add Fitness entities to this integration's already-loaded sensor platform.

    Keeping these entities in a separate module lets the experimental Fitness
    runtime evolve without growing the already large base sensor module. The
    normal Garmin sensor platform is loaded first by ``async_forward_entry_setups``.
    """
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
        # Unit tests and partial platform setup can intentionally mock forwarding.
        # In a real HA runtime this warning is actionable without taking down the
        # otherwise healthy Garmin Connect integration.
        _LOGGER.warning(
            "Garmin Fitness entities were not added because the sensor platform "
            "was not available for config entry %s",
            entry.entry_id,
        )
        return

    await sensor_platform.async_add_entities(
        GarminFitnessSensor(coordinator, description, entry.entry_id)
        for description in FITNESS_SENSOR_DESCRIPTIONS
    )


class GarminFitnessSensor(CoordinatorEntity[FitnessCoordinator], SensorEntity):
    """Representation of one canonical Garmin Fitness metric."""

    entity_description: GarminFitnessSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FitnessCoordinator,
        description: GarminFitnessSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize a Garmin Fitness sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_fitness_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_fitness")},
            name="Garmin Fitness",
            manufacturer="Garmin",
            model="Fitness analytics",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, entry_id),
        )

    @property
    def available(self) -> bool:
        """Return whether Fitness is configured and the series is complete."""
        return (
            super().available
            and bool(self.coordinator.data)
            and bool(self.coordinator.data.get("configured"))
            and bool(self.coordinator.data.get("ready"))
        )

    @property
    def native_value(self) -> float | None:
        """Return the current Fitness value."""
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self.entity_description.key)
        return cast(float | None, value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return calculation provenance without recording the 90-day point list."""
        data = self.coordinator.data or {}
        return {
            "load_source": data.get("load_source"),
            "algorithm_version": data.get("algorithm_version"),
            "max_hr": data.get("max_hr"),
            "sex": data.get("sex"),
            "history_complete": data.get("history_complete", False),
            "history_days": data.get("history_days"),
            "history_start": data.get("history_start"),
            "history_end": data.get("history_end"),
            "blocker_dates": data.get("blocker_dates") or [],
        }
