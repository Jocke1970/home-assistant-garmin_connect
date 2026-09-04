"""Garmin Fitness coordinator.

This is the Home Assistant-facing runtime for the canonical Fitness series. It
reuses the integration's existing authenticated GarminClient. Until the Fitness
engine is available from a released ha-garmin package, this coordinator consumes
the validated read-only probe output; the replacement boundary is deliberately
kept inside this module.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Literal, cast

from aiohttp import ClientError
from ha_garmin import GarminClient
from ha_garmin.exceptions import GarminAuthError, GarminConnectError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FITNESS_MAX_HR,
    CONF_FITNESS_SEX,
    DOMAIN,
    FITNESS_HISTORY_DAYS,
)
from .fitness_probe import build_fitness_probe

_LOGGER = logging.getLogger(__name__)

FITNESS_UPDATE_INTERVAL = timedelta(hours=1)
FITNESS_LOAD_SOURCE = "trimp"
FitnessSex = Literal["male", "female"]


class FitnessCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Provide the current canonical Garmin Fitness values and 90-day history."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GarminClient,
    ) -> None:
        """Initialize the Fitness coordinator using the shared Garmin client."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_fitness",
            update_interval=FITNESS_UPDATE_INTERVAL,
        )
        self.client = client
        raw_max_hr = entry.options.get(CONF_FITNESS_MAX_HR)
        raw_sex = entry.options.get(CONF_FITNESS_SEX)
        self.user_max_hr: float | None = (
            float(raw_max_hr) if raw_max_hr is not None else None
        )
        self.sex: FitnessSex | None = (
            cast(FitnessSex, raw_sex) if raw_sex in ("male", "female") else None
        )

    @property
    def configured(self) -> bool:
        """Return whether both Banister TRIMP profile inputs are configured."""
        return self.user_max_hr is not None and self.sex is not None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the validated 90-day canonical TRIMP training series."""
        if not self.configured:
            return self._empty_data(configured=False)

        user_max_hr = self.user_max_hr
        sex = self.sex
        assert user_max_hr is not None
        assert sex is not None

        try:
            # Temporary adapter boundary: once a distributable ha-garmin Fitness
            # release exists, replace this call with
            # GarminHistoryClient(self.client).fetch_trimp_training_history(...).
            probe = await build_fitness_probe(
                self.client,
                days=FITNESS_HISTORY_DAYS,
                end_date=dt_util.now().date(),
                user_max_hr=user_max_hr,
                sex=sex,
            )
        except GarminAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise UpdateFailed(f"Error fetching Garmin Fitness data: {err}") from err

        training_series = probe.get("training_series") or {}
        trimp_series = training_series.get("trimp") or {}
        latest = trimp_series.get("latest") or {}
        window = probe.get("window") or {}
        blockers = trimp_series.get("blocker_dates") or []
        ready = bool(trimp_series.get("ready")) and bool(latest)

        return {
            "configured": True,
            "ready": ready,
            "daily_load": latest.get("daily_load") if ready else None,
            "ctl": latest.get("ctl") if ready else None,
            "atl": latest.get("atl") if ready else None,
            "tsb": latest.get("tsb") if ready else None,
            "history": trimp_series.get("points") or [],
            "history_days": window.get("days", FITNESS_HISTORY_DAYS),
            "history_start": window.get("start_date"),
            "history_end": window.get("end_date"),
            "history_complete": ready and not blockers,
            "blocker_dates": blockers,
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": probe.get("algorithm_version"),
            "max_hr": user_max_hr,
            "sex": sex,
        }

    def _empty_data(self, *, configured: bool) -> dict[str, Any]:
        """Return a stable data shape before Fitness is configured or available."""
        return {
            "configured": configured,
            "ready": False,
            "daily_load": None,
            "ctl": None,
            "atl": None,
            "tsb": None,
            "history": [],
            "history_days": FITNESS_HISTORY_DAYS,
            "history_start": None,
            "history_end": None,
            "history_complete": False,
            "blocker_dates": [],
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": 1,
            "max_hr": self.user_max_hr,
            "sex": self.sex,
        }
