"""Reusable local product-picture management for Home Assistant cards.

The picture backend started as Garmin Gear-specific functionality. Keep the
legacy Garmin Gear websocket contract intact while exposing the same validated
storage implementation through a neutral collection/key API that other cards
can reuse without knowing which integration currently registers it.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

# Neutral card-picture API. The Garmin integration registers it for now so the
# working Gear implementation can be generalized without a flag-day migration.
WS_UPLOAD_CARD_PICTURE = "card_picture/upload"
WS_REMOVE_CARD_PICTURE = "card_picture/remove"

# Backwards-compatible API used by the already deployed Garmin Gear card.
WS_UPLOAD_GEAR_PICTURE = f"{DOMAIN}/gear_picture/upload"
WS_REMOVE_GEAR_PICTURE = f"{DOMAIN}/gear_picture/remove"

MAX_PICTURE_BYTES = 5 * 1024 * 1024
PICTURE_EXTENSIONS = ("jpeg", "jpg", "png", "webp")

_MIME_TO_EXTENSION = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}
_COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DATA_REGISTERED = f"{DOMAIN}_card_picture_websocket_registered"


def slugify_picture_name(value: str) -> str:
    """Return a safe deterministic filename slug for a card picture key."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


# Compatibility alias for existing tests/imports and the Gear terminology.
def slugify_gear_picture_name(value: str) -> str:
    """Return the canonical local picture slug for a Gear display name."""
    return slugify_picture_name(value)


def validate_picture_collection(value: str) -> str:
    """Validate and return a caller-owned picture collection name."""
    collection = value.strip().lower()
    if not _COLLECTION_RE.fullmatch(collection):
        raise ValueError(
            "Collection måste bestå av a-z, 0-9, bindestreck eller understreck"
        )
    return collection


def _validate_picture_bytes(data: bytes, extension: str) -> None:
    """Validate the minimal image signature before writing a file."""
    valid = False
    if extension == "jpeg":
        valid = data.startswith(b"\xff\xd8\xff")
    elif extension == "png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension == "webp":
        valid = len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if not valid:
        raise ValueError("Bildens innehåll matchar inte filformatet")


def decode_picture(content: str, mime_type: str) -> tuple[str, bytes]:
    """Decode and validate a base64 encoded card picture."""
    extension = _MIME_TO_EXTENSION.get(mime_type.lower())
    if extension is None:
        raise ValueError("Endast JPEG, PNG och WebP stöds")
    try:
        data = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ValueError("Ogiltig bilddata") from err
    if not data:
        raise ValueError("Bildfilen är tom")
    if len(data) > MAX_PICTURE_BYTES:
        raise ValueError("Bildfilen är större än 5 MB")
    _validate_picture_bytes(data, extension)
    return extension, data


# Compatibility alias for the first Gear-specific implementation.
def decode_gear_picture(content: str, mime_type: str) -> tuple[str, bytes]:
    """Decode and validate a base64 encoded Gear picture."""
    return decode_picture(content, mime_type)


def _generic_picture_directory(hass: HomeAssistant, collection: str) -> Path:
    return Path(hass.config.path("www", "card_pictures", collection))


def _legacy_gear_picture_directory(hass: HomeAssistant) -> Path:
    # Do not move existing Gear images. The working frontend probes this path,
    # and preserving it makes the backend migration non-breaking.
    return Path(hass.config.path("www", "gear_pictures"))


def write_picture(directory: Path, slug: str, extension: str, data: bytes) -> Path:
    """Write a picture atomically and remove stale extension variants."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{slug}.{extension}"
    temporary = directory / f".{slug}.{extension}.tmp"
    temporary.write_bytes(data)
    temporary.replace(target)

    for candidate_extension in PICTURE_EXTENSIONS:
        candidate = directory / f"{slug}.{candidate_extension}"
        if candidate != target:
            candidate.unlink(missing_ok=True)
    return target


# Compatibility alias.
def write_gear_picture(directory: Path, slug: str, extension: str, data: bytes) -> Path:
    """Write a Gear picture using the reusable writer."""
    return write_picture(directory, slug, extension, data)


def remove_pictures(directory: Path, slug: str) -> list[str]:
    """Remove all supported picture variants for one key."""
    removed: list[str] = []
    for extension in PICTURE_EXTENSIONS:
        candidate = directory / f"{slug}.{extension}"
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)
    return removed


# Compatibility alias.
def remove_gear_pictures(directory: Path, slug: str) -> list[str]:
    """Remove all supported Gear picture variants."""
    return remove_pictures(directory, slug)


@callback
def async_setup_gear_picture_websocket(hass: HomeAssistant) -> None:
    """Register generic and legacy picture websocket commands once."""
    if hass.data.get(_DATA_REGISTERED):
        return
    websocket_api.async_register_command(hass, websocket_upload_card_picture)
    websocket_api.async_register_command(hass, websocket_remove_card_picture)
    websocket_api.async_register_command(hass, websocket_upload_gear_picture)
    websocket_api.async_register_command(hass, websocket_remove_gear_picture)
    hass.data[_DATA_REGISTERED] = True


async def _async_write_picture(
    hass: HomeAssistant,
    *,
    directory: Path,
    url_prefix: str,
    key: str,
    mime_type: str,
    content: str,
) -> dict[str, str]:
    """Validate and persist one picture, returning its frontend metadata."""
    slug = slugify_picture_name(key)
    if not slug:
        raise ValueError("Kunde inte skapa bildnamn")

    extension, data = decode_picture(content, mime_type)
    target = await hass.async_add_executor_job(
        write_picture,
        directory,
        slug,
        extension,
        data,
    )
    return {
        "slug": slug,
        "filename": target.name,
        "url": f"{url_prefix}/{target.name}",
    }


async def _async_remove_picture(
    hass: HomeAssistant,
    *,
    directory: Path,
    key: str,
) -> tuple[str, list[str]]:
    """Remove all picture variants for one key."""
    slug = slugify_picture_name(key)
    if not slug:
        raise ValueError("Kunde inte skapa bildnamn")
    removed = await hass.async_add_executor_job(remove_pictures, directory, slug)
    return slug, removed


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_UPLOAD_CARD_PICTURE,
        vol.Required("collection"): str,
        vol.Required("key"): str,
        vol.Required("mime_type"): str,
        vol.Required("content"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_upload_card_picture(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Upload or replace a picture in a reusable card-owned collection."""
    try:
        collection = validate_picture_collection(msg["collection"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_collection", str(err))
        return

    if not slugify_picture_name(msg["key"]):
        connection.send_error(msg["id"], "invalid_key", "Kunde inte skapa bildnamn")
        return

    try:
        result = await _async_write_picture(
            hass,
            directory=_generic_picture_directory(hass, collection),
            url_prefix=f"/local/card_pictures/{collection}",
            key=msg["key"],
            mime_type=msg["mime_type"],
            content=msg["content"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_picture", str(err))
        return
    except OSError as err:
        connection.send_error(msg["id"], "save_failed", str(err))
        return

    connection.send_result(msg["id"], {"collection": collection, **result})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_REMOVE_CARD_PICTURE,
        vol.Required("collection"): str,
        vol.Required("key"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_remove_card_picture(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a picture from a reusable card-owned collection."""
    try:
        collection = validate_picture_collection(msg["collection"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_collection", str(err))
        return

    if not slugify_picture_name(msg["key"]):
        connection.send_error(msg["id"], "invalid_key", "Kunde inte skapa bildnamn")
        return

    try:
        slug, removed = await _async_remove_picture(
            hass,
            directory=_generic_picture_directory(hass, collection),
            key=msg["key"],
        )
    except OSError as err:
        connection.send_error(msg["id"], "remove_failed", str(err))
        return

    connection.send_result(
        msg["id"],
        {"collection": collection, "slug": slug, "removed": removed},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_UPLOAD_GEAR_PICTURE,
        vol.Required("name"): str,
        vol.Required("mime_type"): str,
        vol.Required("content"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_upload_gear_picture(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Upload/replace a Gear picture through the reusable picture core."""
    if not slugify_picture_name(msg["name"]):
        connection.send_error(msg["id"], "invalid_name", "Kunde inte skapa bildnamn")
        return

    try:
        result = await _async_write_picture(
            hass,
            directory=_legacy_gear_picture_directory(hass),
            url_prefix="/local/gear_pictures",
            key=msg["name"],
            mime_type=msg["mime_type"],
            content=msg["content"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_picture", str(err))
        return
    except OSError as err:
        connection.send_error(msg["id"], "save_failed", str(err))
        return

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_REMOVE_GEAR_PICTURE,
        vol.Required("name"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_remove_gear_picture(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove local Gear picture variants through the reusable core."""
    if not slugify_picture_name(msg["name"]):
        connection.send_error(msg["id"], "invalid_name", "Kunde inte skapa bildnamn")
        return

    try:
        slug, removed = await _async_remove_picture(
            hass,
            directory=_legacy_gear_picture_directory(hass),
            key=msg["name"],
        )
    except OSError as err:
        connection.send_error(msg["id"], "remove_failed", str(err))
        return

    connection.send_result(msg["id"], {"slug": slug, "removed": removed})