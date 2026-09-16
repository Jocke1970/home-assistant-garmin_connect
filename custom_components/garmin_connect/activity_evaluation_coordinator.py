"""Home Assistant orchestration for recent Garmin activity evaluations."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from ha_garmin import GarminClient
from ha_garmin.exceptions import GarminAuthError, GarminConnectError
from ha_garmin.fitness import (
    ActivityDetailSample,
    ActivityMetrics,
    evaluate_activity,
    parse_activity_detail_samples,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .fitness_coordinator import FitnessCoordinator

_LOGGER = logging.getLogger(__name__)

ACTIVITY_EVALUATION_UPDATE_INTERVAL = timedelta(hours=1)
ACTIVITY_EVALUATION_LIMIT = 5
_CYCLING_ACTIVITY_TYPES = {
    "cycling",
    "road_biking",
    "virtual_ride",
    "indoor_cycling",
    "mountain_biking",
    "gravel_cycling",
    "e_bike_fitness",
    "e_bike_mountain",
}


class ActivityEvaluationCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Evaluate the five most recent activities using cached Fitness context."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GarminClient,
        fitness: FitnessCoordinator,
        body: Any,
    ) -> None:
        """Initialize recent-activity evaluation around existing coordinators."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_activity_evaluation",
            update_interval=ACTIVITY_EVALUATION_UPDATE_INTERVAL,
        )
        self.client = client
        self.fitness = fitness
        self.body = body
        self._detail_cache: dict[int, tuple[ActivityDetailSample, ...]] = {}
        self._selected_activity_id: int | None = None

    @property
    def selected_activity_id(self) -> int | None:
        """Return the currently selected recent activity ID."""
        return self._selected_activity_id

    def select_activity(self, activity_id: int) -> None:
        """Select one already-evaluated activity without refetching Garmin."""
        data = self.data or {}
        evaluations = data.get("evaluations") or []
        selected = next(
            (
                item
                for item in evaluations
                if isinstance(item, dict) and item.get("activity_id") == activity_id
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"Activity {activity_id} is not in the recent evaluation list")

        self._selected_activity_id = activity_id
        updated = dict(data)
        updated["selected_activity_id"] = activity_id
        updated["selected_evaluation"] = selected
        self.async_set_updated_data(updated)

    async def _detail_samples(
        self, activity: ActivityMetrics
    ) -> tuple[ActivityDetailSample, ...]:
        """Fetch and cache only the location-free detail metrics used for evaluation."""
        cached = self._detail_cache.get(activity.activity_id)
        if cached is not None:
            return cached
        if activity.activity_type not in _CYCLING_ACTIVITY_TYPES:
            self._detail_cache[activity.activity_id] = ()
            return ()

        try:
            details = await self.client.get_activity_details(
                activity.activity_id,
                max_chart_size=5000,
                max_poly_size=1,
            )
        except GarminAuthError:
            raise
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            _LOGGER.debug(
                "Could not fetch activity-detail metrics for Garmin activity %s: %s",
                activity.activity_id,
                err,
            )
            return ()

        if not isinstance(details, dict):
            return ()
        samples = parse_activity_detail_samples(details)
        if samples:
            self._detail_cache[activity.activity_id] = samples
        return samples

    def _body_weight_kg(self) -> float | None:
        """Return current body weight when the Body coordinator provides it."""
        data = getattr(self.body, "data", None) or {}
        value = data.get("weightKg") if isinstance(data, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        result = float(value)
        return result if result > 0 else None

    def _post_context(self, activity_date: str) -> dict[str, Any]:
        """Return the canonical daily Fitness state for the activity date."""
        fitness_data = self.fitness.data or {}
        history = fitness_data.get("history") or []
        point = next(
            (
                item
                for item in history
                if isinstance(item, dict) and item.get("date") == activity_date
            ),
            None,
        )
        if point is None:
            return {
                "post_acwr": None,
                "post_strain": None,
                "post_tsb": None,
                "post_context_scope": "day",
            }
        return {
            "post_acwr": point.get("acwr"),
            "post_strain": point.get("strain"),
            "post_tsb": point.get("tsb"),
            "post_context_scope": "day",
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Evaluate recent activities without duplicating Fitness history fetches."""
        if not self.fitness.configured:
            return self._empty_data(configured=False, status="unconfigured")
        if not self.fitness.last_update_success or self.fitness.insight_context is None:
            return self._empty_data(configured=True, status="waiting_for_fitness")

        activities = sorted(
            self.fitness.insight_context.activities,
            key=lambda activity: (activity.start_time, activity.activity_id),
            reverse=True,
        )[:ACTIVITY_EVALUATION_LIMIT]
        if not activities:
            return self._empty_data(configured=True, status="no_activities")

        body_weight_kg = self._body_weight_kg()
        try:
            evaluations: list[dict[str, Any]] = []
            for activity in activities:
                samples = await self._detail_samples(activity)
                evaluated = evaluate_activity(
                    activity,
                    detail_samples=samples,
                    body_weight_kg=body_weight_kg,
                    user_max_hr=self.fitness.user_max_hr,
                )
                serialized = asdict(evaluated)
                serialized.update(self._post_context(evaluated.calendar_date))
                serialized["detail_sample_count"] = len(samples)
                evaluations.append(serialized)
        except GarminAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise UpdateFailed(f"Error evaluating recent Garmin activities: {err}") from err

        valid_ids = {int(item["activity_id"]) for item in evaluations}
        if self._selected_activity_id not in valid_ids:
            self._selected_activity_id = int(evaluations[0]["activity_id"])
        selected = next(
            item
            for item in evaluations
            if int(item["activity_id"]) == self._selected_activity_id
        )

        # Drop cached entries once they leave the five-pass window.
        self._detail_cache = {
            activity_id: samples
            for activity_id, samples in self._detail_cache.items()
            if activity_id in valid_ids
        }

        return {
            "configured": True,
            "status": "ready",
            "ready": True,
            "evaluation_count": len(evaluations),
            "selected_activity_id": self._selected_activity_id,
            "selected_evaluation": selected,
            "evaluations": evaluations,
            "body_weight_kg": body_weight_kg,
            "max_hr": self.fitness.user_max_hr,
            "limit": ACTIVITY_EVALUATION_LIMIT,
        }

    def _empty_data(self, *, configured: bool, status: str) -> dict[str, Any]:
        """Return a stable shape when recent activity evaluation is unavailable."""
        self._selected_activity_id = None
        return {
            "configured": configured,
            "status": status,
            "ready": False,
            "evaluation_count": 0,
            "selected_activity_id": None,
            "selected_evaluation": None,
            "evaluations": [],
            "body_weight_kg": self._body_weight_kg(),
            "max_hr": self.fitness.user_max_hr,
            "limit": ACTIVITY_EVALUATION_LIMIT,
        }
