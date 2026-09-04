"""Tests for Garmin Fitness Recorder statistics backfill."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from homeassistant.components.recorder.models import StatisticMeanType

from custom_components.garmin_connect.fitness_statistics import (
    async_backfill_fitness_statistics,
)


def _history_data(*, complete: bool = True) -> dict:
    return {
        "history_complete": complete,
        "blocker_dates": [] if complete else ["2026-08-05"],
        "history": [
            {
                "date": "2026-09-02",
                "daily_load": 10.0,
                "ctl": 20.0,
                "atl": 30.0,
                "tsb": -10.0,
                "acwr": 0.9,
                "ramp_rate": 1.5,
            },
            {
                "date": "2026-09-03",
                "daily_load": 12.0,
                "ctl": 21.0,
                "atl": 31.0,
                "tsb": -10.0,
                "acwr": 1.1,
                "ramp_rate": 1.0,
            },
            {
                "date": "2026-09-04",
                "daily_load": 5.0,
                "ctl": 19.0,
                "atl": 25.0,
                "tsb": -6.0,
                "acwr": 0.8,
                "ramp_rate": -0.5,
            },
        ],
    }


def test_backfill_imports_completed_days_for_all_fitness_sensors() -> None:
    """Completed historical days are queued under the real sensor statistic IDs."""
    hass = MagicMock()
    hass.config.components = {"recorder"}
    registry = MagicMock()

    def entity_id_for_unique_id(_domain, _platform, unique_id):
        key = unique_id.rsplit("_fitness_", 1)[1]
        return f"sensor.garmin_fitness_{key}"

    registry.async_get_entity_id.side_effect = entity_id_for_unique_id

    with (
        patch(
            "custom_components.garmin_connect.fitness_statistics.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.garmin_connect.fitness_statistics.dt_util.now",
            return_value=datetime(2026, 9, 4, 12, tzinfo=UTC),
        ),
        patch(
            "custom_components.garmin_connect.fitness_statistics.async_import_statistics"
        ) as import_statistics,
    ):
        imported = async_backfill_fitness_statistics(
            hass,
            "entry_1",
            _history_data(),
        )

    assert imported == 12
    assert import_statistics.call_count == 6

    by_statistic_id = {
        call.args[1]["statistic_id"]: (call.args[1], call.args[2])
        for call in import_statistics.call_args_list
    }
    assert set(by_statistic_id) == {
        "sensor.garmin_fitness_daily_load",
        "sensor.garmin_fitness_ctl",
        "sensor.garmin_fitness_atl",
        "sensor.garmin_fitness_tsb",
        "sensor.garmin_fitness_acwr",
        "sensor.garmin_fitness_ramp_rate",
    }

    metadata, statistics = by_statistic_id["sensor.garmin_fitness_ctl"]
    assert metadata["source"] == "recorder"
    assert metadata["unit_of_measurement"] == "TRIMP"
    assert metadata["unit_class"] is None
    assert metadata["mean_type"] == StatisticMeanType.ARITHMETIC
    assert metadata["has_sum"] is False
    assert [row["mean"] for row in statistics] == [20.0, 21.0]
    assert [row["state"] for row in statistics] == [20.0, 21.0]
    assert all(row["start"].hour == 23 for row in statistics)

    acwr_metadata, acwr_statistics = by_statistic_id["sensor.garmin_fitness_acwr"]
    assert acwr_metadata["unit_of_measurement"] is None
    assert [row["mean"] for row in acwr_statistics] == [0.9, 1.1]

    ramp_metadata, ramp_statistics = by_statistic_id[
        "sensor.garmin_fitness_ramp_rate"
    ]
    assert ramp_metadata["unit_of_measurement"] == "TRIMP"
    assert [row["mean"] for row in ramp_statistics] == [1.5, 1.0]


def test_backfill_skips_missing_rolling_metric_values() -> None:
    """A not-yet-available rolling metric is omitted rather than stored as zero."""
    hass = MagicMock()
    hass.config.components = {"recorder"}
    registry = MagicMock()

    def entity_id_for_unique_id(_domain, _platform, unique_id):
        key = unique_id.rsplit("_fitness_", 1)[1]
        return f"sensor.garmin_fitness_{key}"

    registry.async_get_entity_id.side_effect = entity_id_for_unique_id
    data = _history_data()
    data["history"][0]["acwr"] = None
    data["history"][0]["ramp_rate"] = None

    with (
        patch(
            "custom_components.garmin_connect.fitness_statistics.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.garmin_connect.fitness_statistics.dt_util.now",
            return_value=datetime(2026, 9, 4, 12, tzinfo=UTC),
        ),
        patch(
            "custom_components.garmin_connect.fitness_statistics.async_import_statistics"
        ) as import_statistics,
    ):
        imported = async_backfill_fitness_statistics(hass, "entry_1", data)

    # Four base metrics contribute two rows each; ACWR and ramp contribute one each.
    assert imported == 10
    by_statistic_id = {
        call.args[1]["statistic_id"]: call.args[2]
        for call in import_statistics.call_args_list
    }
    assert [row["mean"] for row in by_statistic_id["sensor.garmin_fitness_acwr"]] == [
        1.1
    ]
    assert [
        row["mean"]
        for row in by_statistic_id["sensor.garmin_fitness_ramp_rate"]
    ] == [1.0]


def test_backfill_refuses_incomplete_training_history() -> None:
    """A missing activity day must not silently become a historical zero."""
    hass = MagicMock()
    hass.config.components = {"recorder"}

    with patch(
        "custom_components.garmin_connect.fitness_statistics.async_import_statistics"
    ) as import_statistics:
        imported = async_backfill_fitness_statistics(
            hass,
            "entry_1",
            _history_data(complete=False),
        )

    assert imported == 0
    import_statistics.assert_not_called()


def test_backfill_is_optional_when_recorder_is_not_loaded() -> None:
    """Fitness runtime remains usable on an HA install without Recorder."""
    hass = MagicMock()
    hass.config.components = set()

    with patch(
        "custom_components.garmin_connect.fitness_statistics.async_import_statistics"
    ) as import_statistics:
        imported = async_backfill_fitness_statistics(
            hass,
            "entry_1",
            _history_data(),
        )

    assert imported == 0
    import_statistics.assert_not_called()
