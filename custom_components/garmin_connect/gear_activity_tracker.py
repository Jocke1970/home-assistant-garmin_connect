"""Track the most recent Garmin activity associated with each Gear item.

The tracker is driven by the ActivityCoordinator. It performs one additional
read-only Garmin request only when the latest activityId changes, then stores a
small per-Gear activity summary in Home Assistant storage.

This deliberately avoids polling every Gear item for its activity history.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from ha_garmin.const import GEAR_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import ActivityCoordinator, GarminConnectConfigEntry

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
_STORAGE_KEY = f"{DOMAIN}.gear_last_activity"
_STATE_PREFIX = "sensor.garmin_connect_gear_last_activity"


class GearActivityTracker:
    """Maintain a persistent last-activity cache keyed by Garmin Gear UUID."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectConfigEntry,
        activity_coordinator: ActivityCoordinator,
    ) -> None:
        """Initialize the tracker."""
        self._hass = hass
        self._entry = entry
        self._activity_coordinator = activity_coordinator
        self._client = activity_coordinator.client
        self._lock = asyncio.Lock()
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _STORAGE_VERSION,
            f"{_STORAGE_KEY}.{entry.entry_id}",
        )
        self._last_processed_activity_id: int | None = None
        self._gear_last_activities: dict[str, dict[str, Any]] = {}
        self._unsub_coordinator: Callable[[], None] | None = None
        self._processing_task: asyncio.Task[None] | None = None

    @property
    def entity_id(self) -> str:
        """Return the lightweight state entity used by Lovelace consumers."""
        return f"{_STATE_PREFIX}_{self._entry.entry_id[:8]}"

    async def async_setup(self) -> Callable[[], None]:
        """Load persisted data, subscribe to activity updates and bootstrap."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            activity_id = stored.get("last_processed_activity_id")
            if isinstance(activity_id, int) and activity_id > 0:
                self._last_processed_activity_id = activity_id

            cached = stored.get("gear_last_activities")
            if isinstance(cached, dict):
                self._gear_last_activities = {
                    str(uuid): value
                    for uuid, value in cached.items()
                    if uuid and isinstance(value, dict)
                }

        self._publish_state()
        self._unsub_coordinator = self._activity_coordinator.async_add_listener(
            self._handle_activity_update
        )

        # One safe bootstrap check. If storage already knows this activityId,
        # this is a no-op and makes no extra Garmin request.
        await self._async_process_current_activity()
        return self.async_unload

    @callback
    def _handle_activity_update(self) -> None:
        """Schedule processing after ActivityCoordinator publishes new data."""
        if self._processing_task and not self._processing_task.done():
            return
        self._processing_task = self._hass.async_create_task(
            self._async_process_current_activity(),
            f"{DOMAIN}_gear_last_activity",
        )

    async def _async_process_current_activity(self) -> None:
        """Resolve Gear only when ActivityCoordinator exposes a new activityId."""
        activity = (self._activity_coordinator.data or {}).get("lastActivity") or {}
        if not isinstance(activity, dict):
            return

        activity_id = self._positive_int(activity.get("activityId"))
        if activity_id is None or activity_id == self._last_processed_activity_id:
            return

        async with self._lock:
            # A queued listener may have become stale while waiting for the lock.
            activity = (self._activity_coordinator.data or {}).get("lastActivity") or {}
            if not isinstance(activity, dict):
                return
            activity_id = self._positive_int(activity.get("activityId"))
            if activity_id is None or activity_id == self._last_processed_activity_id:
                return

            try:
                response = await self._client._request(  # noqa: SLF001
                    "GET",
                    GEAR_URL,
                    params={"activityId": str(activity_id)},
                )
            except Exception as err:  # Garmin client already normalizes API errors.
                # Do not advance the processed id. The next activity refresh may
                # retry this read-only lookup instead of silently losing it.
                _LOGGER.debug(
                    "Unable to resolve Gear for Garmin activity %s: %s",
                    activity_id,
                    err,
                )
                return

            gear_items = self._gear_items(response)
            summary = self._activity_summary(activity)

            for gear in gear_items:
                gear_uuid = gear.get("uuid") or gear.get("gearUuid")
                if gear_uuid:
                    self._gear_last_activities[str(gear_uuid)] = summary

            self._last_processed_activity_id = activity_id
            await self._save()
            self._publish_state()

            _LOGGER.debug(
                "Resolved Garmin activity %s to %d Gear item(s)",
                activity_id,
                len(gear_items),
            )

    @staticmethod
    def _gear_items(response: Any) -> list[dict[str, Any]]:
        """Normalize Garmin filterGear responses to a list of dictionaries."""
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if isinstance(response, dict):
            for key in ("gear", "items", "data"):
                value = response.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _activity_summary(cls, activity: dict[str, Any]) -> dict[str, Any]:
        """Keep only the fields Gear Detail needs and make them storage-safe."""
        activity_type = activity.get("activityType")
        if isinstance(activity_type, dict):
            activity_type = activity_type.get("typeKey") or activity_type.get("type_key")

        start = (
            activity.get("startTime")
            or activity.get("startTimeGMT")
            or activity.get("startTimeLocal")
        )

        return {
            "activity_id": cls._positive_int(activity.get("activityId")),
            "activity_name": activity.get("activityName") or "Senaste aktivitet",
            "activity_type": activity_type,
            "start": cls._storage_value(start),
            "distance_m": cls._number(activity.get("distance")),
            "duration_s": cls._number(
                activity.get("duration") or activity.get("elapsedDuration")
            ),
        }

    async def _save(self) -> None:
        """Persist the compact cache after a newly observed activity."""
        await self._store.async_save(
            {
                "last_processed_activity_id": self._last_processed_activity_id,
                "gear_last_activities": self._gear_last_activities,
            }
        )

    @callback
    def _publish_state(self) -> None:
        """Publish the cache as a lightweight state for Gear/Lovelace consumers."""
        self._hass.states.async_set(
            self.entity_id,
            str(len(self._gear_last_activities)),
            {
                "friendly_name": "Garmin Connect Gear Last Activity",
                "icon": "mdi:history",
                "last_processed_activity_id": self._last_processed_activity_id,
                "gear_count": len(self._gear_last_activities),
                "gear_last_activities": self._gear_last_activities,
            },
        )

    @callback
    def async_unload(self) -> None:
        """Unsubscribe and remove the transient state entity."""
        if self._unsub_coordinator:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        self._hass.states.async_remove(self.entity_id)

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @staticmethod
    def _number(value: Any) -> int | float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int | float):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _storage_value(value: Any) -> Any:
        if isinstance(value, datetime | date):
            return value.isoformat()
        if value is None or isinstance(value, str | int | float | bool):
            return value
        return str(value)


async def async_setup_gear_activity_tracker(
    hass: HomeAssistant,
    entry: GarminConnectConfigEntry,
    activity_coordinator: ActivityCoordinator,
) -> Callable[[], None]:
    """Set up event-driven per-Gear last-activity tracking."""
    tracker = GearActivityTracker(hass, entry, activity_coordinator)
    return await tracker.async_setup()
