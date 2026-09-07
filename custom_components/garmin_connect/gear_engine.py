"""Canonical Garmin Gear engine for Home Assistant.

The engine consumes normalized source records from ha-garmin and turns them
into presentation-ready GearItem objects. It intentionally does not merge
records across Garmin identity domains unless a future explicit link proves
that they represent the same physical item.
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
    """Build one canonical item without cross-source merging."""
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


def build_gear_overview(data: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical Home Assistant Gear overview payload."""
    items: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    invalid_record_count = 0

    for raw in data.get("gearRecords") or []:
        if not isinstance(raw, dict):
            invalid_record_count += 1
            continue
        try:
            record = GearSourceRecord.model_validate(raw)
            item = _item_from_record(record)
        except ValidationError:
            invalid_record_count += 1
            continue

        source_counts[record.source] += 1
        for category in item.categories:
            category_counts[category] += 1
        items.append(item.model_dump(mode="json"))

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
