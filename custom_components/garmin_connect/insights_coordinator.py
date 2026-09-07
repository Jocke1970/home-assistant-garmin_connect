"""Home Assistant orchestration for deterministic Garmin Insights V1."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

from aiohttp import ClientError
from ha_garmin import GarminClient, GarminHistoryClient
from ha_garmin.exceptions import GarminAuthError, GarminConnectError
from ha_garmin.insights import (
    INSIGHT_RULESET_VERSION,
    InsightResult,
    InsightSnapshot,
    build_insight_snapshot,
    evaluate_insights,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .fitness_coordinator import FitnessCoordinator

_LOGGER = logging.getLogger(__name__)

INSIGHTS_UPDATE_INTERVAL = timedelta(hours=1)
_SEVERITY_RANK = {
    "positive": 1,
    "info": 2,
    "caution": 3,
    "warning": 4,
}


def _json_value(value: Any) -> Any:
    """Convert dataclass output into HA state-attribute-safe primitives."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _serialize_result(result: InsightResult) -> dict[str, Any]:
    """Serialize one presentation-neutral rule result."""
    return _json_value(asdict(result))


def _recent_activity_summary(snapshot: InsightSnapshot) -> list[dict[str, Any]]:
    """Return small non-location activity context for runtime validation."""
    return [
        {
            "activity_id": activity.activity_id,
            "date": activity.calendar_date.isoformat(),
            "activity_type": activity.activity_type,
            "duration_minutes": activity.duration_minutes,
            "aerobic_training_effect": activity.aerobic_training_effect,
            "anaerobic_training_effect": activity.anaerobic_training_effect,
        }
        for activity in snapshot.recent_activities
    ]


class InsightsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Build the current InsightSnapshot and evaluate deterministic V1 rules."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GarminClient,
        fitness: FitnessCoordinator,
    ) -> None:
        """Initialize Insights around the shared Garmin client and Fitness context."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_insights",
            update_interval=INSIGHTS_UPDATE_INTERVAL,
        )
        self.history_client = GarminHistoryClient(client)
        self.fitness = fitness

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch exact-date recovery and evaluate Insights against cached Fitness."""
        if not self.fitness.configured:
            return self._empty_data(status="unconfigured", configured=False)

        context = self.fitness.insight_context
        personal_trimp_max = self.fitness.insight_personal_trimp_max
        if (
            not self.fitness.last_update_success
            or context is None
            or personal_trimp_max is None
        ):
            return self._empty_data(status="waiting_for_fitness", configured=True)

        as_of = dt_util.now()
        target_date = as_of.date()

        try:
            recovery = await self.history_client.fetch_daily_recovery_metrics(target_date)
            snapshot = build_insight_snapshot(
                as_of,
                recovery=recovery,
                training_history=context.history,
                activities=context.activities,
                personal_trimp_max=personal_trimp_max,
            )
            results = evaluate_insights(snapshot)
        except GarminAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise UpdateFailed(f"Error evaluating Garmin Insights: {err}") from err

        status = (
            max(
                (result.severity for result in results),
                key=_SEVERITY_RANK.__getitem__,
            )
            if results
            else "clear"
        )
        primary = results[0] if results else None

        return {
            "configured": True,
            "status": status,
            "snapshot_complete": snapshot.data_quality.complete,
            "as_of": snapshot.as_of.isoformat(),
            "snapshot_date": target_date.isoformat(),
            "ruleset_version": INSIGHT_RULESET_VERSION,
            "result_count": len(results),
            "result_ids": [result.id for result in results],
            "primary_result_id": primary.id if primary is not None else None,
            "primary_severity": primary.severity if primary is not None else None,
            "primary_confidence": primary.confidence if primary is not None else None,
            "results": [_serialize_result(result) for result in results],
            "data_quality": _json_value(asdict(snapshot.data_quality)),
            "recovery": _json_value(asdict(snapshot.recovery)),
            "training": _json_value(asdict(snapshot.training)),
            "load_focus": _json_value(asdict(snapshot.load_focus)),
            "recent_activity_count": len(snapshot.recent_activities),
            "recent_activities": _recent_activity_summary(snapshot),
        }

    def _empty_data(self, *, status: str, configured: bool) -> dict[str, Any]:
        """Return a stable shape while Insights cannot yet build a snapshot."""
        return {
            "configured": configured,
            "status": status,
            "snapshot_complete": False,
            "as_of": None,
            "snapshot_date": None,
            "ruleset_version": INSIGHT_RULESET_VERSION,
            "result_count": 0,
            "result_ids": [],
            "primary_result_id": None,
            "primary_severity": None,
            "primary_confidence": None,
            "results": [],
            "data_quality": None,
            "recovery": None,
            "training": None,
            "load_focus": None,
            "recent_activity_count": 0,
            "recent_activities": [],
        }
