"""Garmin Fitness coordinator.

This is the Home Assistant-facing runtime for the canonical Fitness series. It
reuses the integration's existing authenticated GarminClient. Until the Fitness
engine is available from a released ha-garmin package, this coordinator consumes
the validated read-only probe output; the replacement boundary is deliberately
kept inside this module.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
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
    FITNESS_ACWR_ACUTE_DAYS,
    FITNESS_ACWR_CHRONIC_DAYS,
    FITNESS_CALCULATION_DAYS,
    FITNESS_HISTORY_DAYS,
    FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,
    FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,
    FITNESS_LOAD_FOCUS_SOURCE,
    FITNESS_RAMP_PERIOD_DAYS,
    FITNESS_RECOVERY_MIN_WARMUP_DAYS,
    FITNESS_STRAIN_HARD_DAY_THRESHOLD,
    FITNESS_STRAIN_SCALE_MAX,
    FITNESS_WARMUP_DAYS,
)
from .fitness_probe import build_fitness_probe
from .fitness_strain import (
    async_fetch_strain_calibration,
    compute_strain_score,
    default_strain_calibration,
)

_LOGGER = logging.getLogger(__name__)

FITNESS_UPDATE_INTERVAL = timedelta(hours=1)
FITNESS_LOAD_SOURCE = "trimp"
FitnessSex = Literal["male", "female"]


def _parse_date(value: Any) -> date | None:
    """Return an ISO calendar date, otherwise None."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _augment_training_metrics(
    points: list[Any],
    *,
    personal_trimp_max: float,
) -> list[dict[str, Any]]:
    """Add ACWR, CTL ramp, and daily strain to a complete training series.

    ACWR/ramp mirror ``ha_garmin.fitness.metrics`` and strain mirrors the
    Fitness core strain helper at the temporary Home Assistant adapter boundary.
    Calculations run on the entire effective warm-up series before the visible
    90-day slice is selected.
    """
    if personal_trimp_max <= 0:
        raise ValueError("personal_trimp_max must be positive")

    normalized: list[dict[str, Any]] = []
    dates: list[date] = []
    loads: list[float] = []
    ctls: list[float] = []

    for raw_point in points:
        if not isinstance(raw_point, dict):
            raise ValueError("Fitness training point must be a mapping")

        point_date = _parse_date(raw_point.get("date"))
        raw_load = raw_point.get("daily_load")
        raw_ctl = raw_point.get("ctl")
        if point_date is None:
            raise ValueError("Fitness training point is missing a valid date")
        if (
            isinstance(raw_load, bool)
            or not isinstance(raw_load, int | float)
            or isinstance(raw_ctl, bool)
            or not isinstance(raw_ctl, int | float)
        ):
            raise ValueError("Fitness training point is missing daily_load or ctl")
        if dates and point_date != dates[-1] + timedelta(days=1):
            raise ValueError("Fitness training series must contain consecutive dates")

        normalized.append(dict(raw_point))
        dates.append(point_date)
        loads.append(float(raw_load))
        ctls.append(float(raw_ctl))

    for index, point in enumerate(normalized):
        point["strain"] = compute_strain_score(loads[index], personal_trimp_max)

        if index >= FITNESS_ACWR_CHRONIC_DAYS - 1:
            acute_window = loads[index - FITNESS_ACWR_ACUTE_DAYS + 1 : index + 1]
            chronic_window = loads[
                index - FITNESS_ACWR_CHRONIC_DAYS + 1 : index + 1
            ]
            acute_average = sum(acute_window) / FITNESS_ACWR_ACUTE_DAYS
            chronic_average = sum(chronic_window) / FITNESS_ACWR_CHRONIC_DAYS
            point["acute_average"] = round(acute_average, 3)
            point["chronic_average"] = round(chronic_average, 3)
            point["acwr"] = (
                round(acute_average / chronic_average, 3)
                if chronic_average > 0
                else None
            )
        else:
            point["acute_average"] = None
            point["chronic_average"] = None
            point["acwr"] = None

        if index >= FITNESS_RAMP_PERIOD_DAYS:
            point["ramp_rate"] = round(
                ctls[index] - ctls[index - FITNESS_RAMP_PERIOD_DAYS],
                3,
            )
        else:
            point["ramp_rate"] = None

    return normalized


def _merge_load_focus_metrics(
    points: list[dict[str, Any]],
    load_focus: Any,
) -> list[dict[str, Any]]:
    """Merge date-aligned daily Training Effect mix into canonical history."""
    raw_points = load_focus.get("points") if isinstance(load_focus, dict) else None
    focus_by_date: dict[str, dict[str, Any]] = {}
    if isinstance(raw_points, list):
        for raw in raw_points:
            if not isinstance(raw, dict):
                continue
            raw_date = raw.get("date")
            if isinstance(raw_date, str):
                focus_by_date[raw_date] = raw

    merged: list[dict[str, Any]] = []
    for point in points:
        item = dict(point)
        point_date = item.get("date")
        focus = focus_by_date.get(point_date) if isinstance(point_date, str) else None
        complete = bool(focus and focus.get("complete") is True)
        item["load_focus_complete"] = complete
        item["load_focus_activity_count"] = (
            int(focus.get("activity_count") or 0) if focus else 0
        )
        item["load_focus_covered_activities"] = (
            int(focus.get("covered_activities") or 0) if focus else 0
        )
        for target, source in (
            ("load_focus_low_aerobic", "low_aerobic"),
            ("load_focus_high_aerobic", "high_aerobic"),
            ("load_focus_anaerobic", "anaerobic"),
        ):
            value = focus.get(source) if focus else None
            item[target] = (
                float(value)
                if not isinstance(value, bool) and isinstance(value, int | float)
                else None
            )
        merged.append(item)
    return merged


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
        raw_max_hr = entry.options.get(CONF_FITNESS_MAX_HR)
        raw_sex = entry.options.get(CONF_FITNESS_SEX)
        self.user_max_hr: float | None = (
            float(raw_max_hr) if raw_max_hr is not None else None
        )
        self.sex: FitnessSex | None = (
            cast(FitnessSex, raw_sex) if raw_sex in ("male", "female") else None
        )
        self._strain_calibration_key: tuple[date, date, float, FitnessSex] | None = None
        self._strain_calibration: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        """Return whether both Banister TRIMP profile inputs are configured."""
        return self.user_max_hr is not None and self.sex is not None

    async def _async_get_strain_calibration(
        self,
        start_date: date,
        end_date: date,
        *,
        user_max_hr: float,
        sex: FitnessSex,
    ) -> dict[str, Any]:
        """Return cached daily strain calibration for the effective history window."""
        key = (start_date, end_date, user_max_hr, sex)
        if self._strain_calibration_key == key and self._strain_calibration is not None:
            return self._strain_calibration

        try:
            calibration = await async_fetch_strain_calibration(
                self.client,
                start_date,
                end_date,
                user_max_hr=user_max_hr,
                sex=sex,
            )
        except GarminAuthError:
            raise
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            _LOGGER.warning(
                "Garmin Fitness strain calibration unavailable; using documented "
                "default personal TRIMP max: %s",
                err,
            )
            calibration = default_strain_calibration(complete=False)

        self._strain_calibration_key = key
        self._strain_calibration = calibration
        return calibration

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch canonical TRIMP history with an EMA warm-up period.

        CTL and ATL are exponential moving averages. Initializing them at the
        left edge of the displayed 90-day window makes historical values drift
        as that window advances. We therefore calculate over 180 days and expose
        only the final 90 days to Home Assistant and Recorder.

        A missing TRIMP activity inside the visible 90-day window always blocks
        the series. A blocker that is only in the older warm-up section may be
        recovered by restarting the strict probe on the following day, but only
        when enough complete warm-up days remain for the EMA seed to decay.
        Missing load is never converted to zero.
        """
        if not self.configured:
            return self._empty_data(configured=False)

        user_max_hr = self.user_max_hr
        sex = self.sex
        assert user_max_hr is not None
        assert sex is not None

        requested_end = dt_util.now().date()

        try:
            # Temporary adapter boundary: once a distributable ha-garmin Fitness
            # release exists, replace this call with
            # GarminHistoryClient(self.client).fetch_trimp_training_history(...).
            probe = await build_fitness_probe(
                self.client,
                days=FITNESS_CALCULATION_DAYS,
                end_date=requested_end,
                user_max_hr=user_max_hr,
                sex=sex,
            )

            calculation_window = probe.get("window") or {}
            calculation_end = (
                _parse_date(calculation_window.get("end_date")) or requested_end
            )
            visible_start = calculation_end - timedelta(
                days=FITNESS_HISTORY_DAYS - 1
            )

            training_series = probe.get("training_series") or {}
            trimp_series = training_series.get("trimp") or {}
            raw_blockers = trimp_series.get("blocker_dates") or []
            blockers = [str(value) for value in raw_blockers]
            parsed_blockers = [_parse_date(value) for value in raw_blockers]

            effective_probe = probe
            effective_series = trimp_series
            remaining_blockers = blockers
            warmup_blocker_dates: list[str] = []
            warmup_recovered = False
            effective_warmup_days = FITNESS_WARMUP_DAYS

            if blockers and all(value is not None for value in parsed_blockers):
                blocker_dates = cast(list[date], parsed_blockers)
                warmup_blocker_dates = [
                    blocker.isoformat()
                    for blocker in blocker_dates
                    if blocker < visible_start
                ]
                last_blocker = max(blocker_dates)
                recovery_start = last_blocker + timedelta(days=1)
                recovery_warmup_days = (visible_start - recovery_start).days
                recovery_days = (calculation_end - recovery_start).days + 1

                can_recover = (
                    last_blocker < visible_start
                    and recovery_warmup_days >= FITNESS_RECOVERY_MIN_WARMUP_DAYS
                    and recovery_days >= FITNESS_HISTORY_DAYS
                )
                if can_recover:
                    recovery_probe = await build_fitness_probe(
                        self.client,
                        days=recovery_days,
                        end_date=calculation_end,
                        user_max_hr=user_max_hr,
                        sex=sex,
                    )
                    recovery_training_series = (
                        recovery_probe.get("training_series") or {}
                    )
                    recovery_series = recovery_training_series.get("trimp") or {}
                    recovery_blockers = recovery_series.get("blocker_dates") or []
                    if bool(recovery_series.get("ready")) and not recovery_blockers:
                        effective_probe = recovery_probe
                        effective_series = recovery_series
                        remaining_blockers = []
                        warmup_recovered = True
                        effective_warmup_days = recovery_warmup_days
                        _LOGGER.debug(
                            "Recovered Garmin Fitness series after warm-up blocker %s "
                            "with %s complete warm-up days",
                            last_blocker,
                            recovery_warmup_days,
                        )

            effective_window = effective_probe.get("window") or {}
            effective_start = _parse_date(effective_window.get("start_date"))
            strain_calibration = (
                await self._async_get_strain_calibration(
                    effective_start,
                    calculation_end,
                    user_max_hr=user_max_hr,
                    sex=sex,
                )
                if effective_start is not None
                else default_strain_calibration(complete=False)
            )
        except GarminAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except (GarminConnectError, ClientError, RuntimeError, ValueError) as err:
            raise UpdateFailed(f"Error fetching Garmin Fitness data: {err}") from err

        all_points = effective_series.get("points") or []
        if not isinstance(all_points, list):
            all_points = []

        raw_personal_trimp_max = strain_calibration.get("personal_trimp_max")
        personal_trimp_max = (
            float(raw_personal_trimp_max)
            if isinstance(raw_personal_trimp_max, int | float)
            and not isinstance(raw_personal_trimp_max, bool)
            else 250.0
        )

        try:
            enriched_points = (
                _augment_training_metrics(
                    all_points,
                    personal_trimp_max=personal_trimp_max,
                )
                if all_points
                else []
            )
            enriched_points = _merge_load_focus_metrics(
                enriched_points,
                effective_probe.get("load_focus"),
            )
        except ValueError as err:
            raise UpdateFailed(f"Error calculating Garmin Fitness metrics: {err}") from err

        visible_points = enriched_points[-FITNESS_HISTORY_DAYS:]
        visible_history_complete = len(visible_points) == FITNESS_HISTORY_DAYS
        latest = visible_points[-1] if visible_points else {}
        load_focus_total_activities = sum(
            int(point.get("load_focus_activity_count") or 0)
            for point in visible_points
            if isinstance(point, dict)
        )
        load_focus_covered_activities = sum(
            int(point.get("load_focus_covered_activities") or 0)
            for point in visible_points
            if isinstance(point, dict)
        )
        load_focus_history_complete = bool(visible_points) and all(
            point.get("load_focus_complete") is True
            for point in visible_points
            if isinstance(point, dict)
        )
        load_focus_incomplete_dates = [
            str(point.get("date"))
            for point in visible_points
            if isinstance(point, dict)
            and point.get("load_focus_complete") is not True
            and isinstance(point.get("date"), str)
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
            bool(effective_series.get("ready"))
            and visible_history_complete
            and bool(latest)
            and not remaining_blockers
        )

        history_start = (
            visible_points[0].get("date")
            if visible_points and isinstance(visible_points[0], dict)
            else None
        )
        history_end = (
            visible_points[-1].get("date")
            if visible_points and isinstance(visible_points[-1], dict)
            else None
        )

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
            "history_start": history_start if ready else None,
            "history_end": history_end if ready else None,
            "history_complete": ready,
            "calculation_days": calculation_window.get(
                "days", FITNESS_CALCULATION_DAYS
            ),
            "calculation_start": calculation_window.get("start_date"),
            "calculation_end": calculation_window.get("end_date"),
            "warmup_days": FITNESS_WARMUP_DAYS,
            "effective_calculation_days": effective_window.get("days"),
            "effective_calculation_start": effective_window.get("start_date"),
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
            "personal_trimp_max": personal_trimp_max,
            "personal_trimp_max_source": strain_calibration.get(
                "personal_trimp_max_source"
            ),
            "strain_calibration_sessions": strain_calibration.get(
                "strain_calibration_sessions"
            ),
            "strain_calibration_min_sessions": strain_calibration.get(
                "strain_calibration_min_sessions"
            ),
            "strain_calibration_multiplier": strain_calibration.get(
                "strain_calibration_multiplier"
            ),
            "strain_calibration_complete": strain_calibration.get(
                "strain_calibration_complete", False
            ),
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": probe.get("algorithm_version"),
            "max_hr": user_max_hr,
            "sex": sex,
        }

    def _empty_data(self, *, configured: bool) -> dict[str, Any]:
        """Return a stable data shape before Fitness is configured or available."""
        strain_calibration = default_strain_calibration(complete=False)
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
            **strain_calibration,
            "load_source": FITNESS_LOAD_SOURCE,
            "algorithm_version": 1,
            "max_hr": self.user_max_hr,
            "sex": self.sex,
        }
