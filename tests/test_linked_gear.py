"""Tests for activity linked-gear enrichment."""

from unittest.mock import AsyncMock

from aiohttp import ClientError
from ha_garmin.const import GEAR_URL

from custom_components.garmin_connect.linked_gear import (
    _CACHE,
    enrich_activity_data_with_linked_gear,
)


def _activity_data() -> dict:
    return {
        "lastActivity": {
            "activityId": 24288164173,
            "activityName": "Test ride",
            "duration": 1586.0,
        },
        "lastActivities": [
            {
                "activityId": 24288164173,
                "activityName": "Test ride",
                "duration": 1586.0,
            }
        ],
    }


async def test_linked_gear_is_exposed_on_latest_activity() -> None:
    """Gear checked on Garmin Connect is exposed as stable HA attributes."""
    _CACHE.clear()
    client = AsyncMock()
    client._request = AsyncMock(
        return_value=[
            {
                "uuid": "17a4e95158cf47a3af83655d90ff9d8c",
                "displayName": "Stages Power L Shimano Ultegra R8100",
                "gearTypeName": "Bike Component",
                "gearMakeName": "Stages",
                "gearModelName": "Stages Power L Shimano Ultegra R8100",
            },
            {
                "uuid": "540c8eeacead401bb7101e870319387e",
                "displayName": "Unknown",
                "customMakeModel": "Bontrager Ion 200 RT Flare",
                "gearTypeName": "Bike Component",
                "gearMakeName": "Bontrager",
                "gearModelName": "Ion 200 RT Flare",
            },
        ]
    )

    data = await enrich_activity_data_with_linked_gear(client, _activity_data())

    client._request.assert_awaited_once_with(
        "GET",
        GEAR_URL,
        params={"activityId": "24288164173"},
    )
    assert data["lastActivity"]["linked_gear_count"] == 2
    assert data["lastActivity"]["linked_gear"][0]["gear_uuid"] == (
        "17a4e95158cf47a3af83655d90ff9d8c"
    )
    assert data["lastActivity"]["linked_gear"][1]["name"] == (
        "Bontrager Ion 200 RT Flare"
    )
    assert data["lastActivities"][0]["linked_gear_count"] == 2


async def test_linked_gear_lookup_is_cached() -> None:
    """Normal activity polling does not hammer Garmin's per-activity gear endpoint."""
    _CACHE.clear()
    client = AsyncMock()
    client._request = AsyncMock(return_value=[])

    await enrich_activity_data_with_linked_gear(client, _activity_data())
    await enrich_activity_data_with_linked_gear(client, _activity_data())

    client._request.assert_awaited_once()


async def test_linked_gear_failure_does_not_break_activity_data() -> None:
    """An optional gear lookup failure leaves the normal activity payload intact."""
    _CACHE.clear()
    client = AsyncMock()
    client._request = AsyncMock(side_effect=ClientError("temporary failure"))
    original = _activity_data()

    data = await enrich_activity_data_with_linked_gear(client, original)

    assert data["lastActivity"]["activityId"] == 24288164173
    assert "linked_gear" not in data["lastActivity"]
