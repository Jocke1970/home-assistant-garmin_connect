"""Optional linked-gear enrichment for Garmin Connect activities."""

from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import ClientError
from ha_garmin import GarminClient
from ha_garmin.const import GEAR_URL
from ha_garmin.exceptions import GarminAuthError, GarminConnectError

_LOGGER = logging.getLogger(__name__)
_CACHE_TTL_SECONDS = 30 * 60
_CACHE: dict[tuple[int, int], tuple[float, list[dict[str, Any]]]] = {}
_GENERIC_NAMES = {"", "unknown", "other"}


def _display_name(item: dict[str, Any], brand: str, model: str, custom: str) -> str:
    """Prefer a useful custom/brand-model name over Garmin's generic Unknown label."""
    candidates = (
        item.get("displayName"),
        item.get("gearName"),
        item.get("name"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text.lower() not in _GENERIC_NAMES:
            return text
    if custom:
        return custom
    brand_model = f"{brand} {model}".strip()
    return brand_model or "Unknown"


def _normalize_linked_gear(raw: Any) -> list[dict[str, Any]]:
    """Return a compact, stable representation of gear linked to an activity."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        nested = None
        for key in ("gear", "items", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                nested = candidate
                break
        if nested is not None:
            items = nested
        elif any(key in raw for key in ("uuid", "gearUuid", "gearUUID", "gear_uuid")):
            items = [raw]
        else:
            items = []
    else:
        items = []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        gear_uuid = (
            item.get("uuid")
            or item.get("gearUuid")
            or item.get("gearUUID")
            or item.get("gear_uuid")
        )
        if not gear_uuid:
            continue

        brand = str(item.get("gearMakeName") or item.get("gearBrand") or item.get("brand") or "").strip()
        model = str(item.get("gearModelName") or item.get("gearModel") or item.get("model") or "").strip()
        custom = str(item.get("customMakeModel") or item.get("custom_make_model") or "").strip()
        name = _display_name(item, brand, model, custom)
        gear_type = item.get("gearTypeName") or item.get("gearType") or item.get("gear_type") or ""
        if isinstance(gear_type, dict):
            gear_type = gear_type.get("typeKey") or gear_type.get("name") or ""

        normalized.append(
            {
                "gear_uuid": str(gear_uuid),
                "name": name,
                "gear_type": str(gear_type),
                "brand": brand,
                "model": model,
                "custom_make_model": custom,
            }
        )

    return normalized


async def _fetch_linked_gear(
    client: GarminClient, activity_id: int
) -> list[dict[str, Any]] | None:
    """Fetch linked gear without making an optional endpoint failure fatal."""
    try:
        raw = await client._request(  # noqa: SLF001 - no public read method exists yet
            "GET",
            GEAR_URL,
            params={"activityId": str(activity_id)},
        )
    except GarminAuthError:
        raise
    except (GarminConnectError, ClientError) as err:
        _LOGGER.debug("Unable to fetch linked gear for activity %s: %s", activity_id, err)
        return None

    return _normalize_linked_gear(raw)


async def enrich_activity_data_with_linked_gear(
    client: GarminClient, data: dict[str, Any]
) -> dict[str, Any]:
    """Add linked_gear attributes to the latest activity.

    Garmin's activity list omits gear associations. The web UI reads them from
    filterGear?activityId=<id>. Cache the optional lookup for 30 minutes so the
    normal activity polling interval does not create an unnecessary API call.
    """
    last_activity = data.get("lastActivity")
    if not isinstance(last_activity, dict):
        return data

    raw_activity_id = last_activity.get("activityId")
    try:
        activity_id = int(raw_activity_id)
    except (TypeError, ValueError):
        return data
    if activity_id <= 0:
        return data

    cache_key = (id(client), activity_id)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        linked_gear = cached[1]
    else:
        linked_gear = await _fetch_linked_gear(client, activity_id)
        if linked_gear is None:
            return data
        _CACHE[cache_key] = (now, linked_gear)
        for key, (stored_at, _) in list(_CACHE.items()):
            if now - stored_at >= _CACHE_TTL_SECONDS:
                _CACHE.pop(key, None)

    last_activity["linked_gear"] = linked_gear
    last_activity["linked_gear_count"] = len(linked_gear)

    recent = data.get("lastActivities")
    if isinstance(recent, list):
        for activity in recent:
            if isinstance(activity, dict) and activity.get("activityId") == raw_activity_id:
                activity["linked_gear"] = linked_gear
                activity["linked_gear_count"] = len(linked_gear)
                break

    return data
