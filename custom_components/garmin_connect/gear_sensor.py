"""Home Assistant entities for the Garmin Gear engine."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GearCoordinator
from .gear_engine import build_gear_overview

_LOGGER = logging.getLogger(__name__)


async def async_add_gear_sensor_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: GearCoordinator,
) -> None:
    """Add canonical Gear entities to the integration's loaded sensor platform."""
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
            "Garmin Gear entities were not added because the sensor platform "
            "was not available for config entry %s",
            entry.entry_id,
        )
        return

    await sensor_platform.async_add_entities(
        [GarminGearOverviewSensor(coordinator, entry.entry_id)]
    )


class GarminGearOverviewSensor(CoordinatorEntity[GearCoordinator], SensorEntity):
    """Canonical summary index for Garmin Gear."""

    _attr_has_entity_name = True
    _attr_name = "Overview"
    _attr_icon = "mdi:store-outline"
    _unrecorded_attributes = frozenset({"items"})

    def __init__(self, coordinator: GearCoordinator, entry_id: str) -> None:
        """Initialize the Garmin Gear overview sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_gear_overview"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_gear")},
            name="Garmin Gear",
            manufacturer="Garmin",
            model="Gear engine",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _overview(self) -> dict[str, Any]:
        return build_gear_overview(self.coordinator.data or {})

    @property
    def native_value(self) -> int:
        """Return the number of canonical Gear items."""
        return int(self._overview()["item_count"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the canonical Gear index and summary counts."""
        overview = self._overview()
        return {
            key: value
            for key, value in overview.items()
            if key != "item_count"
        }
