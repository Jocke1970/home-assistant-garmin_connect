"""Diagnostics support for Garmin Connect."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

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

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinators": coordinator_info,
        "gear_probe": _gear_probe_data(gear_data),
    }
