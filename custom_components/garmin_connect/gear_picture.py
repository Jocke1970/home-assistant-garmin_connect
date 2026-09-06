"""Reusable local product-picture management for Home Assistant cards.

The implementation lives in Garmin Connect because Garmin Gear introduced the
feature first, but the storage and websocket contract are card-agnostic. Cards
provide a collection and stable key; this module validates, stores and removes
the image under that card's own ``www/<collection>_card/pictures`` directory.
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

# Reusable API for all HA cards using this backend.
WS_UPLOAD_CARD_PICTURE = f"{DOMAIN}/card_picture/upload"
WS_REMOVE_CARD_PICTURE = f"{DOMAIN}/card_picture/remove"

# Compatibility API for the first Garmin Gear frontend. These commands use the
# exact same generic implementation and canonical Garmin Gear picture folder.
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
_GARMIN_GEAR_COLLECTION = "garmin_gear"


def slugify_picture_name(value: str) -> str:
    """Return a safe deterministic filename slug for a card picture key."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


# Compatibility alias for existing imports/tests using Gear terminology.
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


def picture_collection_folder(collection: str) -> str:
    """Return the canonical www folder owned by one card collection."""
    return f"{validate_picture_collection(collection)}_card"


def picture_url_prefix(collection: str) -> str:
    """Return the public /local URL prefix for one card picture collection."""
    return f"/local/{picture_collection_folder(collection)}/pictures"


def _picture_directory(hass: HomeAssistant, collection: str) -> Path:
    return Path(
        hass.config.path(
            "www",
            picture_collection_folder(collection),
            "pictures",
        )
    )


def _legacy_gear_picture_directory(hass: HomeAssistant) -> Path:
    """Return the pre-migration Gear folder, used only for cleanup."""
    return Path(hass.config.path("www", "gear_pictures"))


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


# Compatibility alias for existing imports/tests.
def decode_gear_picture(content: str, mime_type: str) -> tuple[str, bytes]:
    """Decode and validate a base64 encoded Gear picture."""
    return decode_picture(content, mime_type)


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


async def _async_write_picture(
    hass: HomeAssistant,
    *,
    collection: str,
    key: str,
    mime_type: str,
    content: str,
) -> dict[str, str]:
    """Validate and persist one picture, returning its frontend metadata."""
    collection = validate_picture_collection(collection)
    slug = slugify_picture_name(key)
    if not slug:
        raise ValueError("Kunde inte skapa bildnamn")

    extension, data = decode_picture(content, mime_type)
    target = await hass.async_add_executor_job(
        write_picture,
        _picture_directory(hass, collection),
        slug,
        extension,
        data,
    )

    # The pre-generic Garmin Gear backend stored files directly in
    # /config/www/gear_pictures. Once a Gear picture is replaced, remove that
    # stale copy so it can never reappear as a frontend fallback.
    if collection == _GARMIN_GEAR_COLLECTION:
        await hass.async_add_executor_job(
            remove_pictures,
            _legacy_gear_picture_directory(hass),
            slug,
        )

    return {
        "collection": collection,
        "slug": slug,
        "filename": target.name,
        "url": f"{picture_url_prefix(collection)}/{target.name}",
    }


async def _async_remove_picture(
    hass: HomeAssistant,
    *,
    collection: str,
    key: str,
) -> tuple[str, list[str]]:
    """Remove all picture variants for one collection/key pair."""
    collection = validate_picture_collection(collection)
    slug = slugify_picture_name(key)
    if not slug:
        raise ValueError("Kunde inte skapa bildnamn")

    removed = await hass.async_add_executor_job(
        remove_pictures,
        _picture_directory(hass, collection),
        slug,
    )
    if collection == _GARMIN_GEAR_COLLECTION:
        legacy_removed = await hass.async_add_executor_job(
            remove_pictures,
            _legacy_gear_picture_directory(hass),
            slug,
        )
        removed.extend(legacy_removed)
    return slug, removed


@callback
def async_setup_gear_picture_websocket(hass: HomeAssistant) -> None:
    """Register reusable and compatibility picture websocket commands once."""
    if hass.data.get(_DATA_REGISTERED):
        return
    websocket_api.async_register_command(hass, websocket_upload_card_picture)
    websocket_api.async_register_command(hass, websocket_remove_card_picture)
    websocket_api.async_register_command(hass, websocket_upload_gear_picture)
    websocket_api.async_register_command(hass, websocket_remove_gear_picture)
    hass.data[_DATA_REGISTERED] = True


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
        result = await _async_write_picture(
            hass,
            collection=msg["collection"],
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

    connection.send_result(msg["id"], result)


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
        slug, removed = await _async_remove_picture(
            hass,
            collection=collection,
            key=msg["key"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_picture", str(err))
        return
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
    """Compatibility wrapper for the original Garmin Gear frontend."""
    try:
        result = await _async_write_picture(
            hass,
            collection=_GARMIN_GEAR_COLLECTION,
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
    """Compatibility wrapper for the original Garmin Gear frontend."""
    try:
        slug, removed = await _async_remove_picture(
            hass,
            collection=_GARMIN_GEAR_COLLECTION,
            key=msg["name"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_picture", str(err))
        return
    except OSError as err:
        connection.send_error(msg["id"], "remove_failed", str(err))
        return

    connection.send_result(msg["id"], {"slug": slug, "removed": removed})
