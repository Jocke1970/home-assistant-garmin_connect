"""Diagnostics support for Garmin Connect."""

from __future__ import annotations

from dataclasses import fields
from typing import Any
from urllib.parse import quote

from ha_garmin.const import GARMIN_CONNECT_API
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import GarminConnectConfigEntry

TO_REDACT = {
    "token",
    "refresh_token",
    "client_id",
    "displayName",
    "fullName",
    "userName",
    "email",
    "profileImageUrlMedium",
    "profileImageUrlSmall",
    "profileImageUrlLarge",
    "userProfilePk",
    "profileId",
}

DEVICE_PROBE_REDACT = {
    "deviceId",
    "unitId",
    "serialNumber",
    "applicationKey",
    "userDeviceId",
    "registrationId",
}

_DEVICE_SETTINGS_TARGETS = (
    "edge 1040",
    "fenix 7",
    "fēnix 7",
    "index sleep",
)
_DEVICE_SETTINGS_INTERESTING_TERMS = (
    "battery",
    "charge",
    "remaining",
    "percent",
)
_DEVICE_STATUS_INTERESTING_TERMS = (
    "battery",
    "charge",
    "remaining",
    "percent",
    "sync",
    "status",
    "connected",
    "upload",
)


def _gear_probe_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return raw Gear payloads for diagnostics, with account identifiers redacted.

    Garmin expanded Gear tracking in 2026 beyond distance-only usage. Keep the
    probe in diagnostics rather than entity attributes so we can inspect the
    currently returned schema without polluting Recorder or changing entity
    semantics while field names are still being established.
    """
    gear = data.get("gear")
    gear_stats = data.get("gearStats")

    return async_redact_data(
        {
            "gear": gear if isinstance(gear, list) else [],
            "gearStats": gear_stats if isinstance(gear_stats, list) else [],
        },
        TO_REDACT,
    )


def _device_probe_name(device: dict[str, Any]) -> str:
    """Return a useful non-sensitive product name for a registered device."""
    return str(
        device.get("productDisplayName")
        or device.get("deviceTypeSimpleName")
        or device.get("displayName")
        or "Garmin device"
    ).strip()


def _is_device_settings_target(device: dict[str, Any]) -> bool:
    """Return whether a device is one of the current battery-discovery targets."""
    haystack = " ".join(
        str(device.get(key) or "")
        for key in ("productDisplayName", "deviceTypeSimpleName", "displayName")
    ).lower()
    return any(target in haystack for target in _DEVICE_SETTINGS_TARGETS)


def _collect_interesting_settings_fields(
    value: Any, path: tuple[str, ...] = ()
) -> list[dict[str, Any]]:
    """Collect battery/charge-like scalar fields from a nested settings payload."""
    matches: list[dict[str, Any]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            matches.extend(_collect_interesting_settings_fields(child, child_path))
        return matches

    if isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                _collect_interesting_settings_fields(child, (*path, f"[{index}]"))
            )
        return matches

    dotted_path = ".".join(path)
    lowered_path = dotted_path.lower()
    if any(term in lowered_path for term in _DEVICE_SETTINGS_INTERESTING_TERMS):
        matches.append({"path": dotted_path, "value": value})
    return matches


def _collect_interesting_status_fields(
    value: Any, path: tuple[str, ...] = ()
) -> list[dict[str, Any]]:
    """Collect battery/status/sync-like scalar fields from a nested payload."""
    matches: list[dict[str, Any]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            matches.extend(_collect_interesting_status_fields(child, child_path))
        return matches

    if isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                _collect_interesting_status_fields(child, (*path, f"[{index}]"))
            )
        return matches

    dotted_path = ".".join(path)
    lowered_path = dotted_path.lower()
    if any(term in lowered_path for term in _DEVICE_STATUS_INTERESTING_TERMS):
        matches.append({"path": dotted_path, "value": value})
    return matches


def _summarize_status_payload(value: Any) -> dict[str, Any]:
    """Summarize a discovery payload without dumping unrelated device data."""
    if isinstance(value, dict):
        return {
            "response_type": "dict",
            "top_level_keys": list(value.keys()),
            "interesting_fields": _collect_interesting_status_fields(value),
        }
    if isinstance(value, list):
        return {
            "response_type": "list",
            "item_count": len(value),
            "interesting_fields": _collect_interesting_status_fields(value),
        }
    return {
        "response_type": type(value).__name__,
        "interesting_fields": [],
    }


async def _device_status_probe(client: Any, devices: Any) -> dict[str, Any]:
    """Probe candidate Garmin device status/sync endpoints for battery discovery."""

    async def _call_url(url: str) -> dict[str, Any]:
        try:
            payload = await client._request("GET", url)
        except Exception as err:  # Diagnostics must survive experimental endpoints.
            return {"error": type(err).__name__, "message": str(err)}
        return _summarize_status_payload(payload)

    per_device: list[dict[str, Any]] = []
    if isinstance(devices, list):
        for device in devices:
            if not isinstance(device, dict) or not _is_device_settings_target(device):
                continue

            entry: dict[str, Any] = {"name": _device_probe_name(device)}
            device_id = device.get("deviceId")
            if isinstance(device_id, bool) or not isinstance(device_id, int):
                entry["device_info"] = {"error": "missing_device_id"}
            else:
                url = (
                    f"{GARMIN_CONNECT_API}/device-service/deviceservice/"
                    f"device-info/{device_id}"
                )
                entry["device_info"] = await _call_url(url)
            per_device.append(entry)

    primary_url = (
        f"{GARMIN_CONNECT_API}/web-gateway/device-info/primary-training-device"
    )
    primary_training_device = await _call_url(primary_url)

    active_device: dict[str, Any]
    try:
        profile = await client.get_user_profile()
        display_name = getattr(profile, "display_name", None)
    except Exception as err:  # Keep diagnostics useful if profile lookup fails.
        active_device = {"error": type(err).__name__, "message": str(err)}
    else:
        if display_name:
            active_url = (
                f"{GARMIN_CONNECT_API}/device-service/deviceservice/device-info/active/"
                f"{quote(str(display_name), safe='')}"
            )
            active_device = await _call_url(active_url)
        else:
            active_device = {"error": "missing_display_name"}

    return {
        "per_device": per_device,
        "primary_training_device": primary_training_device,
        "active_device": active_device,
    }


async def _device_settings_probe(
    client: Any, devices: Any
) -> list[dict[str, Any]]:
    """Probe settings for selected Garmin devices without exposing device identifiers."""
    if not isinstance(devices, list):
        return []

    results: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict) or not _is_device_settings_target(device):
            continue

        entry: dict[str, Any] = {"name": _device_probe_name(device)}
        device_id = device.get("deviceId")
        if isinstance(device_id, bool) or not isinstance(device_id, int):
            entry["error"] = "missing_device_id"
            results.append(entry)
            continue

        try:
            settings = await client.get_device_settings(device_id)
        except Exception as err:  # Diagnostics must survive a single probe failure.
            entry["error"] = type(err).__name__
            results.append(entry)
            continue

        if not isinstance(settings, dict):
            entry["settings_type"] = type(settings).__name__
            entry["interesting_fields"] = []
            results.append(entry)
            continue

        entry["top_level_keys"] = list(settings.keys())
        entry["interesting_fields"] = _collect_interesting_settings_fields(settings)
        results.append(entry)

    return results


async def _device_battery_probe(client: Any) -> dict[str, Any]:
    """Fetch raw authenticated device/sensor payloads only for diagnostics.

    These endpoints are intentionally not added to normal polling yet. The probe
    lets us inspect Garmin's current battery schema for registered devices and
    paired ANT+/BLE sensors without polluting Recorder or guessing field names.
    """

    async def _call(method: Any) -> Any:
        try:
            return await method()
        except Exception as err:  # Diagnostics must remain available if one probe fails.
            return {"error": type(err).__name__, "message": str(err)}

    devices = await _call(client.get_devices)
    sensors = await _call(client.get_sensors)
    last_used = await _call(client.get_device_last_used)
    device_settings = await _device_settings_probe(client, devices)
    device_status = await _device_status_probe(client, devices)

    results = {
        "devices": devices,
        "sensors": sensors,
        "last_used": last_used,
        "device_settings": device_settings,
        "device_status": device_status,
    }

    return async_redact_data(results, DEVICE_PROBE_REDACT)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GarminConnectConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinators = entry.runtime_data

    coordinator_info: dict[str, Any] = {}
    for field in fields(coordinators):
        coordinator = getattr(coordinators, field.name)
        data = coordinator.data or {}
        data_keys = list(data.keys())
        coordinator_info[field.name] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "data_keys_count": len(data_keys),
            "data_keys_sample": data_keys[:50] if len(data_keys) > 50 else data_keys,
        }

    gear_data = coordinators.gear.data or {}
    device_battery_probe = await _device_battery_probe(coordinators.gear.client)

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinators": coordinator_info,
        "gear_probe": _gear_probe_data(gear_data),
        "device_battery_probe": device_battery_probe,
    }
