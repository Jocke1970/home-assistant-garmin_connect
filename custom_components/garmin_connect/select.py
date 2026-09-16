"""Select platform for Garmin recent activity evaluation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .activity_evaluation_coordinator import ActivityEvaluationCoordinator
from .activity_evaluation_presentation import (
    activity_option_label,
    normalize_activity_evaluation_language,
)
from .const import ACTIVITY_EVALUATION_DATA_KEY, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the recent activity selector."""
    coordinator = hass.data.get(ACTIVITY_EVALUATION_DATA_KEY, {}).get(entry.entry_id)
    if not isinstance(coordinator, ActivityEvaluationCoordinator):
        return
    async_add_entities([GarminActivityEvaluationSelect(coordinator, entry.entry_id)])


class GarminActivityEvaluationSelect(
    CoordinatorEntity[ActivityEvaluationCoordinator], SelectEntity
):
    """Select one of the five most recent evaluated Garmin activities."""

    _attr_has_entity_name = False
    _attr_name = "Garmin Activity Evaluation"
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(
        self,
        coordinator: ActivityEvaluationCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize recent-pass selector."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_activity_evaluation_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_activity_evaluation")},
            name="Garmin Activity Evaluation",
            manufacturer="Garmin",
            model="Recent activity evaluation",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _language(self) -> str:
        """Return current HA language in the supported set."""
        config = getattr(self.coordinator.hass, "config", None)
        language = getattr(config, "language", None)
        return normalize_activity_evaluation_language(
            language if isinstance(language, str) else None
        )

    def _option_map(self) -> dict[str, int]:
        """Build unique human-readable option labels mapped to activity IDs."""
        data = self.coordinator.data or {}
        raw_evaluations = data.get("evaluations") or []
        today = dt_util.now().date()
        labels: list[tuple[str, int]] = []
        for item in raw_evaluations:
            if not isinstance(item, dict):
                continue
            activity_id = item.get("activity_id")
            if isinstance(activity_id, bool) or not isinstance(activity_id, int):
                continue
            labels.append(
                (
                    activity_option_label(
                        item,
                        self._language(),
                        today=today,
                    ),
                    activity_id,
                )
            )

        totals = Counter(label for label, _ in labels)
        seen: Counter[str] = Counter()
        result: dict[str, int] = {}
        for label, activity_id in labels:
            seen[label] += 1
            unique_label = (
                f"{label} · {seen[label]}" if totals[label] > 1 else label
            )
            result[unique_label] = activity_id
        return result

    @property
    def available(self) -> bool:
        """Return whether recent activity evaluations are ready."""
        return (
            super().available
            and bool(self.coordinator.data)
            and bool(self.coordinator.data.get("ready"))
            and bool(self.options)
        )

    @property
    def options(self) -> list[str]:
        """Return localized labels for the five most recent evaluations."""
        return list(self._option_map())

    @property
    def current_option(self) -> str | None:
        """Return the label matching the currently selected activity."""
        selected_id = self.coordinator.selected_activity_id
        if selected_id is None:
            return None
        return next(
            (
                label
                for label, activity_id in self._option_map().items()
                if activity_id == selected_id
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Select an already evaluated pass without another Garmin request."""
        option_map = self._option_map()
        if option not in option_map:
            raise ValueError(f"Unknown activity evaluation option: {option}")
        self.coordinator.select_activity(option_map[option])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose only selector provenance, not duplicate activity payloads."""
        return {
            "evaluation_count": (self.coordinator.data or {}).get(
                "evaluation_count", 0
            ),
            "selected_activity_id": self.coordinator.selected_activity_id,
        }
