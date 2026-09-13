"""Canonical Garmin Gear engine for Home Assistant.

The engine consumes normalized source records from ha-garmin and turns them
into presentation-ready GearItem objects. Garmin identity domains stay
separate in the source records; only explicitly confirmed physical links are
combined into one presentation item.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ha_garmin import GearItem, GearSourceRecord
from pydantic import ValidationError

GEAR_SCHEMA_VERSION = "1.0"

_ACTIVITY_CATEGORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("cycling", "biking", "virtual_ride", "indoor_cycling"), "cycling"),
    (("running", "trail_running", "treadmill_running"), "running"),
    (("hiking",), "hiking"),
    (("strength", "weight_training"), "strength"),
    (("rowing", "cardio", "elliptical", "walking"), "cardio"),
    (("ski", "snowboard", "skate"), "winter_sport"),
)

# These links are based on observed Garmin source identities from the user's
# account. They are intentionally explicit: no display-name auto matching is
# performed across Garmin identity domains.
_BONTRAGER_GEAR_UUID = "540c8eeacead401bb7101e870319387e"
_BONTRAGER_SENSOR_SOURCE_ID = "garmin_sensor:1f8eafdc59256ed2"
_VARIA_GEAR_UUID = "c4d8a6db863f4907bd0b1d4c06d9d9ef"
_VARIA_SENSOR_SOURCE_ID = "garmin_sensor:90cf2b37799261be"
_SPEED_SENSOR_GEAR_UUID = "054f917179d8489db3e76cdd5606bf64"
_MORPHEUS_GEAR_UUID = "220a3e46556d43eda2d95200faee1340"


def _add_category(categories: list[str], category: str) -> None:
    """Append one already-normalized category once."""
    if category not in categories:
        categories.append(category)


def _activity_type_keys(record: GearSourceRecord) -> list[str]:
    """Extract activity type keys from normalized Gear metadata."""
    metadata = record.metadata
    keys: list[str] = []

    associated = metadata.get("associated_activity_types")
    if isinstance(associated, list):
        for item in associated:
            if not isinstance(item, dict):
                continue
            value = item.get("activityTypeKey") or item.get("typeKey")
            if value:
                keys.append(str(value).lower())

    defaults = metadata.get("default_for_activity")
    if isinstance(defaults, list):
        for value in defaults:
            if value:
                keys.append(str(value).lower())

    return keys


def _activity_categories(record: GearSourceRecord) -> list[str]:
    """Resolve broad categories from Garmin activity metadata."""
    categories: list[str] = []
    for key in _activity_type_keys(record):
        for needles, category in _ACTIVITY_CATEGORY_RULES:
            if any(needle in key for needle in needles):
                _add_category(categories, category)
    return categories


def _classify_gear_record(record: GearSourceRecord) -> tuple[list[str], str]:
    """Classify a Garmin Gear registry record from structured metadata."""
    metadata = record.metadata
    gear_type = str(metadata.get("gear_type") or "").upper()
    categories = _activity_categories(record)

    if gear_type == "BIKE":
        _add_category(categories, "cycling")
        return categories, "cycling"

    if gear_type == "BIKE_COMPONENT":
        _add_category(categories, "cycling")
        _add_category(categories, "accessories")
        return categories, "accessories"

    if gear_type in {"SKIS", "SKI", "SNOWBOARD", "SKATES", "SKATE"}:
        _add_category(categories, "winter_sport")
        return categories, "winter_sport"

    if categories:
        return categories, categories[0]

    return ["other"], "other"


def _classify_device_record(record: GearSourceRecord) -> tuple[list[str], str]:
    """Classify registered Garmin hardware from Garmin device categories."""
    raw_categories = record.metadata.get("device_categories")
    device_categories = (
        [str(value).upper() for value in raw_categories]
        if isinstance(raw_categories, list)
        else []
    )
    categories: list[str] = []

    if any("BIKE" in value for value in device_categories):
        _add_category(categories, "cycling")
    if any("SCALE" in value or "WEIGHT" in value for value in device_categories):
        _add_category(categories, "scales")
    if any("SLEEP" in value or "RECOVERY" in value for value in device_categories):
        _add_category(categories, "recovery")
    if any("WATCH" in value or "WEARABLE" in value for value in device_categories):
        _add_category(categories, "wearables")

    if not categories:
        return ["other"], "other"

    for preferred in ("cycling", "scales", "recovery", "wearables"):
        if preferred in categories:
            return categories, preferred
    return categories, categories[0]


def _classify_sensor_record(record: GearSourceRecord) -> tuple[list[str], str]:
    """Classify recent ANT+/BLE sensors from Garmin sensor type."""
    sensor_type = str(record.metadata.get("sensor_type") or "").upper()
    categories = ["sensors"]

    if sensor_type.startswith("BIKE_") or any(
        token in sensor_type for token in ("CADENCE", "POWER", "SPEED")
    ):
        _add_category(categories, "cycling")
    if "LIGHT" in sensor_type:
        _add_category(categories, "accessories")
    if "HEART_RATE" in sensor_type or sensor_type.startswith("HR_"):
        _add_category(categories, "cardio")

    return categories, "sensors"


def classify_record(record: GearSourceRecord) -> tuple[list[str], str]:
    """Return categories and primary category for one source record."""
    if record.source == "garmin_gear":
        return _classify_gear_record(record)
    if record.source == "garmin_device":
        return _classify_device_record(record)
    if record.source == "garmin_sensor":
        return _classify_sensor_record(record)
    return ["other"], "other"


def _item_from_record(record: GearSourceRecord) -> GearItem:
    """Build one canonical item from one source record."""
    categories, primary_category = classify_record(record)
    return GearItem(
        id=record.source_id,
        name=record.name or "Unknown Gear",
        manufacturer=record.manufacturer,
        model=record.model,
        garmin_ids=dict(record.garmin_ids),
        categories=categories,
        primary_category=primary_category,
        sources=[record],
        active=record.active,
        last_used_at=record.last_used_at,
        last_seen_at=record.last_seen_at,
        activity_count=record.activity_count,
        metadata=dict(record.metadata),
    )


def _sensor_text(record: GearSourceRecord, key: str) -> str:
    """Return one sensor metadata value as normalized uppercase text."""
    return str(record.metadata.get(key) or "").strip().upper()


def _sensor_id_text(record: GearSourceRecord, key: str) -> str:
    """Return one normalized Garmin sensor id value as text."""
    return str(record.garmin_ids.get(key) or "").strip().upper()


def _is_confirmed_sensor_link(
    gear: GearSourceRecord, sensor: GearSourceRecord
) -> bool:
    """Return whether two source records are a confirmed physical association."""
    if gear.source != "garmin_gear" or sensor.source != "garmin_sensor":
        return False

    gear_uuid = str(gear.garmin_ids.get("gear_uuid") or "")

    if gear_uuid == _BONTRAGER_GEAR_UUID:
        return sensor.source_id == _BONTRAGER_SENSOR_SOURCE_ID

    if gear_uuid == _VARIA_GEAR_UUID:
        # Garmin currently exposes the Varia radar through the recent-sensors
        # endpoint as HEART_RATE. The stable serial-based sensor identity proves
        # that this is the same source that previously looked like an HR sensor.
        return sensor.source_id == _VARIA_SENSOR_SOURCE_ID

    if gear_uuid == _SPEED_SENSOR_GEAR_UUID:
        return (
            _sensor_text(sensor, "sensor_type") == "BIKE_SPEED"
            and str(sensor.manufacturer or "").upper() == "GARMIN"
            and _sensor_id_text(sensor, "product_id") == "9"
            and _sensor_id_text(sensor, "part_number") == "9"
        )

    if gear_uuid == _MORPHEUS_GEAR_UUID:
        return (
            _sensor_text(sensor, "sensor_type") == "HEART_RATE"
            and str(sensor.manufacturer or "").upper() == "FITCARE"
            and _sensor_id_text(sensor, "product_id") == "5"
            and _sensor_text(sensor, "software_version") == "0.3"
        )

    return False


def _item_from_confirmed_link(
    gear: GearSourceRecord, sensor: GearSourceRecord
) -> GearItem:
    """Build one presentation item while retaining both Garmin source records."""
    gear_categories, primary_category = classify_record(gear)
    sensor_categories, _ = classify_record(sensor)
    categories = list(gear_categories)
    for category in sensor_categories:
        _add_category(categories, category)

    garmin_ids = dict(gear.garmin_ids)
    for key, value in sensor.garmin_ids.items():
        garmin_ids.setdefault(key, value)

    metadata = dict(gear.metadata)
    metadata.update(sensor.metadata)
    metadata["physical_link"] = "confirmed"
    metadata["linked_sensor_source_id"] = sensor.source_id

    return GearItem(
        id=gear.source_id,
        name=gear.name or sensor.name or "Unknown Gear",
        manufacturer=gear.manufacturer or sensor.manufacturer,
        model=gear.model or sensor.model,
        garmin_ids=garmin_ids,
        categories=categories,
        primary_category=primary_category,
        sources=[gear, sensor],
        active=gear.active,
        last_used_at=gear.last_used_at,
        last_seen_at=sensor.last_seen_at or gear.last_seen_at,
        activity_count=gear.activity_count,
        metadata=metadata,
    )


def _build_items(records: list[GearSourceRecord]) -> list[GearItem]:
    """Build physical presentation items using only confirmed cross-source links."""
    consumed_sensor_ids: set[str] = set()
    items: list[GearItem] = []

    for record in records:
        if record.source == "garmin_sensor" and record.source_id in consumed_sensor_ids:
            continue

        if record.source == "garmin_gear":
            linked_sensor = next(
                (
                    candidate
                    for candidate in records
                    if candidate.source == "garmin_sensor"
                    and candidate.source_id not in consumed_sensor_ids
                    and _is_confirmed_sensor_link(record, candidate)
                ),
                None,
            )
            if linked_sensor is not None:
                consumed_sensor_ids.add(linked_sensor.source_id)
                items.append(_item_from_confirmed_link(record, linked_sensor))
                continue

        items.append(_item_from_record(record))

    return items


def build_gear_overview(data: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical Home Assistant Gear overview payload."""
    records: list[GearSourceRecord] = []
    source_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    invalid_record_count = 0

    for raw in data.get("gearRecords") or []:
        if not isinstance(raw, dict):
            invalid_record_count += 1
            continue
        try:
            record = GearSourceRecord.model_validate(raw)
        except ValidationError:
            invalid_record_count += 1
            continue

        records.append(record)
        source_counts[record.source] += 1

    canonical_items = _build_items(records)
    items = [item.model_dump(mode="json") for item in canonical_items]

    for item in canonical_items:
        for category in item.categories:
            category_counts[category] += 1

    active_count = sum(item.get("active") is True for item in items)
    inactive_count = sum(item.get("active") is False for item in items)
    unknown_active_count = len(items) - active_count - inactive_count

    return {
        "schema_version": GEAR_SCHEMA_VERSION,
        "item_count": len(items),
        "active_count": active_count,
        "inactive_count": inactive_count,
        "unknown_active_count": unknown_active_count,
        "invalid_record_count": invalid_record_count,
        "source_counts": dict(source_counts),
        "category_counts": dict(category_counts),
        "items": items,
    }
