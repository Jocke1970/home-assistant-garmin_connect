"""Garmin Fitness coordinator.

This Home Assistant-facing runtime orchestrates the canonical Fitness series
using the shared authenticated GarminClient. Garmin API history normalization and
all Fitness calculations live in ha-garmin; this module owns only orchestration,
Home Assistant state shape, warm-up recovery and presentation provenance.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Literal, cast

from aiohttp import ClientError
from ha_garmin import GarminClient, GarminHistoryClient
from ha_garmin.exceptions import GarminAuthError, GarminConnectError
from ha_garmin.fitness import (
    build_daily_load_focus_series,
    calibrate_personal_trimp_max,
    compute_strain_score,
    compute_trimp,
)
from ha_garmin.fitness.const import (
    DEFAULT_PERSONAL_TRIMP_MAX,
    GARMIN_FITNESS_ALGORITHM_VERSION,
)
from ha_garmin.history import TrimpTrainingContext
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FITNESS_MAX_HR,
    CONF_FITNESS_SEX,
    DOMAIN,
    FITNESS_ACWR_ACUTE_DAYS,
    FITNESS_ACWR_CHRONIC_DAYS,
    FITNESS_CALCULATION_DAYS,
    FITNESS_HISTORY_DAYS,
    FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,
    FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
    FITNESS_LOAD_FOCUS_SOURCE,
    FITNESS_RAMP_PERIOD_DAYS,
    FITNESS_RECOVERY_MIN_WARMUP_DAYS,
    FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
    FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
    FITNESS_STRAIN_HARD_DAY_THRESHOLD,
    FITNESS_STRAIN_SCALE_MAX,
    FITNESS_WARMUP_DAYS,
)

_LOGGER = logging.getLogger(__name__)

FITNESS_UPDATE_INTERVAL = timedelta(hours=1)
FITNESS_LOAD_SOURCE = "trimp"
FitnessSex = Literal["male", "female"]


def _strain_calibration(
    context: TrimpTrainingContext,
    *,
    user_max_hr: float,
    sex: FitnessSex,
) -> dict[str, Any]:
    """Build strain calibration metadata using only ha-garmin Fitness math."""
    session_trimps: list[float] = []
    for activity in context.activities:
        resting_hr = context.resting_hr_by_date.get(activity.calendar_date)
        if resting_hr is None:
            continue
        value = compute_trimp(activity, resting_hr, user_max_hr, sex)
        if value is not None and value > 0:
            session_trimps.append(value)

    calibrated = calibrate_personal_trimp_max(
        session_trimps,
        min_sessions=FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        multiplier=FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
    )
    personal_trimp_max = (
        calibrated if calibrated is not None else DEFAULT_PERSONAL_TRIMP_MAX
    )
    return {
        "personal_trimp_max": personal_trimp_max,
        "personal_trimp_max_source": (
            "calibrated" if calibrated is not None else "default"
        ),
        "strain_calibration_sessions": len(session_trimps),
        "strain_calibration_min_sessions": FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
        "strain_calibration_multiplier": FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
        "strain_calibration_complete": True,
    }


def _history_points(
    context: TrimpTrainingContext,
    *,
    personal_trimp_max: float,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Serialize ha-garmin Fitness result objects into the HA history shape."""
    history = context.history
    if not history.assessment.ready:
        return []

    acwr_by_date = {point.date: point for point in history.acwr_points}
    ramp_by_date = {point.date: point for point in history.ramp_rate_points}
    focus_by_date = {
        point.date: point
        for point in build_daily_load_focus_series(
            context.activities,
            start_date,
            end_date,
            high_aerobic_threshold=FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
        )
    }

    result: list[dict[str, Any]] = []
    for point in history.training_points:
        acwr = acwr_by_date.get(point.date)
        ramp = ramp_by_date.get(point.date)
        focus = focus_by_date.get(point.date)
        result.append(
            {
                "date": point.date.isoformat(),
                "daily_load": point.daily_load,
                "ctl": point.ctl,
                "atl": point.atl,
                "tsb": point.tsb,
                "acute_average": acwr.acute_average if acwr is not None else None,
                "chronic_average": (
                    acwr.chronic_average if acwr is not None else None
                ),
                "acwr": acwr.acwr if acwr is not None else None,
                "ramp_rate": ramp.ramp_rate if ramp is not None else None,
                "strain": compute_strain_score(
                    point.daily_load,
                    personal_trimp_max,
                ),
                "load_focus_complete": bool(focus and focus.complete),
                "load_focus_activity_count": (
                    focus.activity_count if focus is not None else 0
                ),
                "load_focus_covered_activities": (
                    focus.covered_activities if focus is not None else 0
                ),
                "load_focus_low_aerobic": (
                    focus.low_aerobic if focus is not None else None
                ),
                "load_focus_high_aerobic": (
                    focus.high_aerobic if focus is not None else None
                ),
                "load_focus_anaerobic": (
                    focus.anaerobic if focus is not None else None
                ),
            }
        )
    return result


class FitnessCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Provide current Garmin Fitness values and stable 90-day history."""

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
        self.history_client = GarminHistoryClient(client)
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

    async def _fetch_context(
        self,
        start_date: date,
        end_date: date,
        *,
        user_max_hr: float,
        sex: FitnessSex,
    ) -> TrimpTrainingContext:
        """Fetch one strict Fitness context through the ha-garmin boundary."""
        return await self.history_client.fetch_trimp_training_context(
            start_date,
            end_date,
            user_max_hr=user_max_hr,
            sex=sex,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch canonical TRIMP history with a stable EMA warm-up period."""
        if not self.configured:
            return self._empty_data(configured=False)

        user_max_hr = self.user_max_hr
        sex = self.sex
        assert user_max_hr is not None
        assert sex is not None

        calculation_end = dt_util.now().date()
        calculation_start = calculation_end - timedelta(
            days=FITNESS_CALCULATION_DAYS - 1
        )
        visible_start = calculation_end - timedelta(days=FITNESS_HISTORY_DAYS - 1)

        try:
            context = await self._fetch_context(
                calculation_start,
                calculation_end,
                user_max_hr=user_max_hr,
                sex=sex,
            )

            blockers = list(context.history.assessment.incomplete_days)
            remaining_blockers = [value.isoformat() for value in blockers]
            warmup_blocker_dates = [
                value.isoformat() for value in blockers if value < visible_start
            ]
            warmup_recovered = False
            effective_start = calculation_start
            effective_warmup_days = FITNESS_WARMUP_DAYS
            effective_context = context

            if blockers:
                last_blocker = max(blockers)
                recovery_start = last_blocker + timedelta(days=1)
                recovery_warmup_days = (visible_start - recovery_start).days
                recovery_days = (calculation_end - recovery_start).days + 1
                can_recover = (
                    last_blocker < visible_start
                    and recovery_warmup_days >= FITNESS_RECOVERY_MIN_WARMUP_DAYS
                    and recovery_days >= FITNESS_HISTORY_DAYS
                )
                if can_recover:
                    recovery_context = await self._fetch_context(
                        recovery_start,
                        calculation_end,
                        user_max_hr=user_max_hr,
                        sex=sex,
                    )
                    if recovery_context.history.assessment.ready:
                        effective_context = recovery_context
                        effective_start = recovery_start
                        remaining_blockers = []
                        warmup_recovered = True
                        effective_warmup_days = recovery_warmup_days
                        _LOGGER.debug(
                            "Recovered Garmin Fitness series after warm-up blocker %s "
                            "with %s complete warm-up days",
                            last_blocker,
                            recovery_warmup_days,
                        )

            strain_calibration = _strain_calibration(
                effective_context,
                user_max_hr=user_max_hr,
                sex=sex,
            )
        except GarminAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise UpdateFailed(f"Error fetching Garmin Fitness data: {err}") from err

        personal_trimp_max = float(strain_calibration["personal_trimp_max"])
        try:
            all_points = _history_points(
                effective_context,
                personal_trimp_max=personal_trimp_max,
                start_date=effective_start,
                end_date=calculation_end,
            )
        except ValueError as err:
            raise UpdateFailed(f"Error calculating Garmin Fitness metrics: {err}") from err

        visible_points = all_points[-FITNESS_HISTORY_DAYS:]
        visible_history_complete = len(visible_points) == FITNESS_HISTORY_DAYS
        latest = visible_points[-1] if visible_points else {}

        load_focus_total_activities = sum(
            int(point.get("load_focus_activity_count") or 0)
            for point in visible_points
        )
        load_focus_covered_activities = sum(
            int(point.get("load_focus_covered_activities") or 0)
            for point in visible_points
        )
        load_focus_history_complete = bool(visible_points) and all(
            point.get("load_focus_complete") is True for point in visible_points
        )
        load_focus_incomplete_dates = [
            str(point["date"])
            for point in visible_points
            if point.get("load_focus_complete") is not True
        ]
        load_focus_coverage_percent = (
            round(
                load_focus_covered_activities
                / load_focus_total_activities
                * 100.0,
                1,
            )
            if load_focus_total_activities
            else 100.0
        )

        ready = (
            effective_context.history.assessment.ready
            and visible_history_complete
            and bool(latest)
            and not remaining_blockers
        )
        effective_calculation_days = (
            calculation_end - effective_start
        ).days + 1

        return {
            "configured": True,
            "ready": ready,
            "daily_load": latest.get("daily_load") if ready else None,
            "ctl": latest.get("ctl") if ready else None,
            "atl": latest.get("atl") if ready else None,
            "tsb": latest.get("tsb") if ready else None,
            "acwr": latest.get("acwr") if ready else None,
            "ramp_rate": latest.get("ramp_rate") if ready else None,
            "strain": latest.get("strain") if ready else None,
            "load_focus_low_aerobic": (
                latest.get("load_focus_low_aerobic") if ready else None
            ),
            "load_focus_high_aerobic": (
                latest.get("load_focus_high_aerobic") if ready else None
            ),
            "load_focus_anaerobic": (
                latest.get("load_focus_anaerobic") if ready else None
            ),
            "history": visible_points if ready else [],
            "history_days": FITNESS_HISTORY_DAYS,
            "history_start": visible_points[0]["date"] if ready else None,
            "history_end": visible_points[-1]["date"] if ready else None,
            "history_complete": ready,
            "calculation_days": FITNESS_CALCULATION_DAYS,
            "calculation_start": calculation_start.isoformat(),
            "calculation_end": calculation_end.isoformat(),
            "warmup_days": FITNESS_WARMUP_DAYS,
            "effective_calculation_days": effective_calculation_days,
            "effective_calculation_start": effective_start.isoformat(),
            "effective_warmup_days": effective_warmup_days,
            "warmup_recovered": warmup_recovered,
            "warmup_blocker_dates": warmup_blocker_dates,
            "blocker_dates": remaining_blockers,
            "acwr_acute_days": FITNESS_ACWR_ACUTE_DAYS,
            "acwr_chronic_days": FITNESS_ACWR_CHRONIC_DAYS,
            "ramp_period_days": FITNESS_RAMP_PERIOD_DAYS,
            "strain_scale_max": FITNESS_STRAIN_SCALE_MAX,
            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,
            "load_focus_algorithm_version": FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,
            "load_focus_source": FITNESS_LOAD_FOCUS_SOURCE,
            "load_focus_high_aerobic_threshold": (
                FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD
            ),
            "load_focus_history_complete": (
                load_focus_history_complete if ready else False
            ),
            "load_focus_activity_coverage_percent": (
                load_focus_coverage_percent if ready else None
            ),
            "load_focus_total_activities": (
                load_focus_total_activities if ready else None
            ),
            "load_focus_covered_activities": (
                load_focus_covered_activities if ready else None
            ),
            "load_focus_incomplete_dates": (
                load_focus_incomplete_dates if ready else []
            ),
            **strain_calibration,
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": effective_context.history.algorithm_version,
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
            "acwr": None,
            "ramp_rate": None,
            "strain": None,
            "load_focus_low_aerobic": None,
            "load_focus_high_aerobic": None,
            "load_focus_anaerobic": None,
            "history": [],
            "history_days": FITNESS_HISTORY_DAYS,
            "history_start": None,
            "history_end": None,
            "history_complete": False,
            "calculation_days": FITNESS_CALCULATION_DAYS,
            "calculation_start": None,
            "calculation_end": None,
            "warmup_days": FITNESS_WARMUP_DAYS,
            "effective_calculation_days": FITNESS_CALCULATION_DAYS,
            "effective_calculation_start": None,
            "effective_warmup_days": FITNESS_WARMUP_DAYS,
            "warmup_recovered": False,
            "warmup_blocker_dates": [],
            "blocker_dates": [],
            "acwr_acute_days": FITNESS_ACWR_ACUTE_DAYS,
            "acwr_chronic_days": FITNESS_ACWR_CHRONIC_DAYS,
            "ramp_period_days": FITNESS_RAMP_PERIOD_DAYS,
            "strain_scale_max": FITNESS_STRAIN_SCALE_MAX,
            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,
            "load_focus_algorithm_version": FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,
            "load_focus_source": FITNESS_LOAD_FOCUS_SOURCE,
            "load_focus_high_aerobic_threshold": (
                FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD
            ),
            "load_focus_history_complete": False,
            "load_focus_activity_coverage_percent": None,
            "load_focus_total_activities": None,
            "load_focus_covered_activities": None,
            "load_focus_incomplete_dates": [],
            "personal_trimp_max": DEFAULT_PERSONAL_TRIMP_MAX,
            "personal_trimp_max_source": "default_unavailable",
            "strain_calibration_sessions": None,
            "strain_calibration_min_sessions": FITNESS_STRAIN_CALIBRATION_MIN_SESSIONS,
            "strain_calibration_multiplier": FITNESS_STRAIN_CALIBRATION_MULTIPLIER,
            "strain_calibration_complete": False,
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": GARMIN_FITNESS_ALGORITHM_VERSION,
            "max_hr": self.user_max_hr,
            "sex": self.sex,
        }
