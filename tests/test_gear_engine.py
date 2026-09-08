"""Tests for the canonical Garmin Gear Home Assistant layer."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import Platform

from custom_components.garmin_connect.coordinator import GearCoordinator
from custom_components.garmin_connect.gear_engine import build_gear_overview
from custom_components.garmin_connect.gear_sensor import (
    GarminGearOverviewSensor,
    async_add_gear_sensor_entities,
)

_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry_1"
    entry.options = {}
    return entry


def _coordinator() -> GearCoordinator:
    return GearCoordinator(MagicMock(), _entry(), AsyncMock(), AsyncMock())


def _sample_data() -> dict:
    return {
        "gearRecords": [
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:gear123",
                "name": "Bontrager Ion 200 RT Flare",
                "manufacturer": "Bontrager",
                "model": "Ion 200 RT Flare",
                "garmin_ids": {
                    "gear_uuid": "gear123",
                    "gear_v2_uuid": "gear-v2-123",
                },
                "active": True,
                "last_used_at": "2026-09-05T12:00:00+00:00",
                "last_seen_at": None,
                "activity_count": 3,
                "metadata": {
                    "gear_type": "BIKE_COMPONENT",
                    "usage_type": "DURATION",
                },
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:abc123",
                "name": "Bike Light Main",
                "manufacturer": None,
                "model": None,
                "garmin_ids": {"sensor_identity_hash": "abc123"},
                "active": None,
                "last_used_at": None,
                "last_seen_at": "2026-09-05T12:51:00+00:00",
                "activity_count": None,
                "metadata": {
                    "sensor_type": "BIKE_LIGHT_MAIN",
                    "battery_status": "OK",
                },
            },
        ]
    }


def _confirmed_link_data() -> dict:
    return {
        "gearRecords": [
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:c4d8a6db863f4907bd0b1d4c06d9d9ef",
                "name": "Garmin Varia 511",
                "manufacturer": "Garmin",
                "model": "Varia 511",
                "garmin_ids": {
                    "gear_uuid": "c4d8a6db863f4907bd0b1d4c06d9d9ef"
                },
                "active": True,
                "last_used_at": "2026-09-08T14:26:26+00:00",
                "last_seen_at": None,
                "activity_count": 123,
                "metadata": {"gear_type": "OTHER", "usage_type": "DISTANCE"},
            },
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:054f917179d8489db3e76cdd5606bf64",
                "name": "Garmin Speedsensor 2",
                "manufacturer": "Garmin",
                "model": "Speedsensor 2",
                "garmin_ids": {
                    "gear_uuid": "054f917179d8489db3e76cdd5606bf64"
                },
                "active": True,
                "last_used_at": "2026-09-08T14:26:26+00:00",
                "last_seen_at": None,
                "activity_count": 1,
                "metadata": {"gear_type": "BIKE_COMPONENT"},
            },
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:220a3e46556d43eda2d95200faee1340",
                "name": "Morpheus M7",
                "manufacturer": "Morpheus",
                "model": "M7",
                "garmin_ids": {
                    "gear_uuid": "220a3e46556d43eda2d95200faee1340"
                },
                "active": True,
                "last_used_at": None,
                "last_seen_at": None,
                "activity_count": 0,
                "metadata": {"gear_type": "OTHER", "usage_type": "NONE"},
            },
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:540c8eeacead401bb7101e870319387e",
                "name": "Bontrager Ion 200 RT Flare",
                "manufacturer": "Bontrager",
                "model": "Ion 200 RT Flare",
                "garmin_ids": {
                    "gear_uuid": "540c8eeacead401bb7101e870319387e"
                },
                "active": True,
                "last_used_at": "2026-09-05T12:00:00+00:00",
                "last_seen_at": None,
                "activity_count": 7,
                "metadata": {"gear_type": "BIKE_COMPONENT"},
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:90cf2b37799261be",
                "name": "Varia",
                "manufacturer": None,
                "model": None,
                "garmin_ids": {
                    "sensor_identity_hash": "90cf2b37799261be",
                    "serial_hash": "77e5859eb17ff4ea",
                },
                "active": None,
                "last_used_at": None,
                "last_seen_at": "2026-09-08T14:26:48+00:00",
                "activity_count": None,
                "metadata": {
                    "sensor_type": "HEART_RATE",
                    "battery_level": 75,
                    "battery_status": "OK",
                    "software_version": "0.3",
                    "identity_strength": "strong",
                },
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:speed123",
                "name": "Speed",
                "manufacturer": "GARMIN",
                "model": "9",
                "garmin_ids": {
                    "sensor_identity_hash": "speed123",
                    "product_id": 9,
                    "part_number": "9",
                },
                "active": None,
                "last_used_at": None,
                "last_seen_at": "2026-09-08T14:26:48+00:00",
                "activity_count": None,
                "metadata": {
                    "sensor_type": "BIKE_SPEED",
                    "battery_status": "OK",
                    "software_version": "2.3",
                },
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:morpheus123",
                "name": "Heart Rate",
                "manufacturer": "FITCARE",
                "model": "5",
                "garmin_ids": {
                    "sensor_identity_hash": "morpheus123",
                    "product_id": 5,
                    "part_number": "5",
                },
                "active": None,
                "last_used_at": None,
                "last_seen_at": "2026-09-08T14:26:48+00:00",
                "activity_count": None,
                "metadata": {
                    "sensor_type": "HEART_RATE",
                    "battery_level": 100,
                    "battery_status": "NEW",
                    "software_version": "0.3",
                    "identity_strength": "strong",
                },
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:1f8eafdc59256ed2",
                "name": "Bike Light Main",
                "manufacturer": None,
                "model": None,
                "garmin_ids": {
                    "sensor_identity_hash": "1f8eafdc59256ed2"
                },
                "active": None,
                "last_used_at": None,
                "last_seen_at": "2026-09-05T12:51:00+00:00",
                "activity_count": None,
                "metadata": {
                    "sensor_type": "BIKE_LIGHT_MAIN",
                    "battery_status": "OK",
                },
            },
        ]
    }


def test_overview_keeps_used_seen_and_nullable_count_separate() -> None:
    overview = build_gear_overview(_sample_data())

    assert overview["schema_version"] == "1.0"
    assert overview["item_count"] == 2
    assert overview["active_count"] == 1
    assert overview["unknown_active_count"] == 1
    assert overview["source_counts"] == {"garmin_gear": 1, "garmin_sensor": 1}

    gear, sensor = overview["items"]
    assert gear["last_used_at"] == "2026-09-05T12:00:00Z"
    assert gear["last_seen_at"] is None
    assert gear["activity_count"] == 3
    assert sensor["last_used_at"] is None
    assert sensor["last_seen_at"] == "2026-09-05T12:51:00Z"
    assert sensor["activity_count"] is None
    assert "device_id" not in gear
    assert "device_id" not in sensor


def test_categories_are_lowercase_snake_case_and_primary_is_member() -> None:
    overview = build_gear_overview(_sample_data())

    for item in overview["items"]:
        assert item["primary_category"] in item["categories"]
        assert all(_CATEGORY_RE.fullmatch(category) for category in item["categories"])

    gear, sensor = overview["items"]
    assert gear["primary_category"] == "accessories"
    assert set(gear["categories"]) >= {"cycling", "accessories"}
    assert sensor["primary_category"] == "sensors"
    assert set(sensor["categories"]) >= {"sensors", "cycling", "accessories"}


def test_overview_items_are_prepared_for_multiple_source_records() -> None:
    overview = build_gear_overview(_sample_data())

    assert all(len(item["sources"]) == 1 for item in overview["items"])
    assert overview["items"][0]["sources"][0]["source_id"] == "garmin_gear:gear123"


def test_overview_merges_only_confirmed_physical_sensor_links() -> None:
    overview = build_gear_overview(_confirmed_link_data())

    assert overview["item_count"] == 4
    assert overview["active_count"] == 4
    assert overview["unknown_active_count"] == 0
    assert overview["source_counts"] == {"garmin_gear": 4, "garmin_sensor": 4}

    items = {item["name"]: item for item in overview["items"]}

    varia = items["Garmin Varia 511"]
    assert len(varia["sources"]) == 2
    assert varia["metadata"]["physical_link"] == "confirmed"
    assert varia["metadata"]["sensor_type"] == "HEART_RATE"
    assert varia["metadata"]["battery_level"] == 75
    assert varia["last_seen_at"] == "2026-09-08T14:26:48Z"
    assert varia["sources"][1]["source_id"] == "garmin_sensor:90cf2b37799261be"

    speed = items["Garmin Speedsensor 2"]
    assert len(speed["sources"]) == 2
    assert speed["metadata"]["sensor_type"] == "BIKE_SPEED"
    assert speed["metadata"]["software_version"] == "2.3"
    assert speed["garmin_ids"]["product_id"] == 9

    morpheus = items["Morpheus M7"]
    assert len(morpheus["sources"]) == 2
    assert morpheus["metadata"]["sensor_type"] == "HEART_RATE"
    assert morpheus["metadata"]["battery_level"] == 100
    assert morpheus["sources"][1]["manufacturer"] == "FITCARE"

    bontrager = items["Bontrager Ion 200 RT Flare"]
    assert len(bontrager["sources"]) == 2
    assert bontrager["metadata"]["sensor_type"] == "BIKE_LIGHT_MAIN"


def test_overview_does_not_merge_unconfirmed_same_name_records() -> None:
    data = {
        "gearRecords": [
            {
                "source": "garmin_gear",
                "source_id": "garmin_gear:not-confirmed",
                "name": "Example Sensor",
                "garmin_ids": {"gear_uuid": "not-confirmed"},
                "active": True,
                "metadata": {"gear_type": "OTHER"},
            },
            {
                "source": "garmin_sensor",
                "source_id": "garmin_sensor:not-confirmed",
                "name": "Example Sensor",
                "garmin_ids": {"sensor_identity_hash": "not-confirmed"},
                "metadata": {"sensor_type": "HEART_RATE"},
            },
        ]
    }

    overview = build_gear_overview(data)

    assert overview["item_count"] == 2
    assert all(len(item["sources"]) == 1 for item in overview["items"])


def test_overview_sensor_belongs_to_garmin_gear_service_device() -> None:
    coordinator = _coordinator()
    coordinator.data = _sample_data()
    sensor = GarminGearOverviewSensor(coordinator, "entry_1")

    assert sensor.native_value == 2
    assert sensor.unique_id == "entry_1_gear_overview"
    assert sensor.device_info is not None
    assert sensor.device_info["name"] == "Garmin Gear"
    assert sensor.device_info["model"] == "Gear engine"
    assert sensor.extra_state_attributes["schema_version"] == "1.0"
    assert sensor.extra_state_attributes["items"]


async def test_add_gear_entity_uses_loaded_garmin_sensor_platform() -> None:
    hass = MagicMock()
    entry = _entry()
    coordinator = _coordinator()
    platform = MagicMock()
    platform.domain = Platform.SENSOR
    platform.config_entry = entry
    platform.async_add_entities = AsyncMock()

    with patch(
        "custom_components.garmin_connect.gear_sensor.async_get_platforms",
        return_value=[platform],
    ):
        await async_add_gear_sensor_entities(hass, entry, coordinator)

    platform.async_add_entities.assert_awaited_once()
    entities = list(platform.async_add_entities.await_args.args[0])
    assert len(entities) == 1
    assert entities[0].unique_id == "entry_1_gear_overview"
