"""Recorder statistics backfill for Garmin Fitness analytics."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from homeassistant.components.recorder import DOMAIN as RECORDER_DOMAIN
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .fitness_sensor import FITNESS_SENSOR_DESCRIPTIONS, FITNESS_UNIT

_LOGGER = logging.getLogger(__name__)


@callback
def async_backfill_fitness_statistics(
    hass: HomeAssistant,
    entry_id: str,
    data: dict[str, Any],
) -> int:
    """Backfill completed Fitness days into Recorder long-term statistics.

    The imported statistic IDs are the actual Garmin Fitness sensor entity IDs,
    resolved from their stable unique IDs. ``async_import_statistics`` performs
    an upsert for an existing statistic ID/timestamp, so repeating this backfill
    after a restart is safe and can repair historical gaps.

    Today's point is intentionally excluded. The live sensor and Recorder own
    the current day; only completed calendar days are imported here.
    """
    if RECORDER_DOMAIN not in hass.config.components:
        _LOGGER.debug("Skipping Garmin Fitness backfill because Recorder is not loaded")
        return 0

    if not data.get("history_complete"):
        blockers = data.get("blocker_dates") or []
        _LOGGER.debug(
            "Skipping Garmin Fitness backfill because history is incomplete: %s",
            blockers,
        )
        return 0

    history = data.get("history")
    if not isinstance(history, list) or not history:
        return 0

    today = dt_util.now().date()
    registry = er.async_get(hass)
    imported_rows = 0

    for description in FITNESS_SENSOR_DESCRIPTIONS:
        unique_id = f"{entry_id}_fitness_{description.key}"
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR,
            DOMAIN,
            unique_id,
        )
        if entity_id is None:
            _LOGGER.debug(
                "Skipping Garmin Fitness %s backfill because its entity is not registered",
                description.key,
            )
            continue

        statistics: list[StatisticData] = []
        for point in history:
            if not isinstance(point, dict):
                continue

            raw_date = point.get("date")
            value = point.get(description.key)
            if not isinstance(raw_date, str) or isinstance(value, bool):
                continue
            if not isinstance(value, int | float):
                continue

            try:
                point_date = date.fromisoformat(raw_date)
            except ValueError:
                continue

            if point_date >= today:
                continue

            numeric_value = float(value)
            # Store the canonical end-of-day value at 23:00 local time. This is
            # an hourly Recorder boundary and keeps each point on its Garmin
            # calendar date when displayed in Home Assistant.
            start = dt_util.start_of_local_day(point_date).replace(hour=23)
            statistics.append(
                StatisticData(
                    start=start,
                    state=numeric_value,
                    mean=numeric_value,
                    min=numeric_value,
                    max=numeric_value,
                )
            )

        if not statistics:
            continue

        metadata = StatisticMetaData(
            source=RECORDER_DOMAIN,
            statistic_id=entity_id,
            name=None,
            unit_of_measurement=FITNESS_UNIT,
            unit_class=None,
            mean_type=StatisticMeanType.ARITHMETIC,
            has_sum=False,
        )
        async_import_statistics(hass, metadata, statistics)
        imported_rows += len(statistics)

    if imported_rows:
        _LOGGER.debug(
            "Queued %s Garmin Fitness long-term statistic rows for backfill",
            imported_rows,
        )
    return imported_rows
