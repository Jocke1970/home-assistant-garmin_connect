"""Local product-picture management for Garmin Gear."""

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
_DATA_REGISTERED = f"{DOMAIN}_gear_picture_websocket_registered"


def slugify_gear_picture_name(value: str) -> str:
    """Return the canonical local picture slug for a Gear display name."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


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


def decode_gear_picture(content: str, mime_type: str) -> tuple[str, bytes]:
    """Decode and validate a base64 encoded Gear picture."""
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


def _picture_directory(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("www", "gear_pictures"))


def write_gear_picture(directory: Path, slug: str, extension: str, data: bytes) -> Path:
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


def remove_gear_pictures(directory: Path, slug: str) -> list[str]:
    """Remove all supported picture variants for a Gear item."""
    removed: list[str] = []
    for extension in PICTURE_EXTENSIONS:
        candidate = directory / f"{slug}.{extension}"
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)
    return removed


@callback
def async_setup_gear_picture_websocket(hass: HomeAssistant) -> None:
    """Register Gear picture websocket commands once per HA runtime."""
    if hass.data.get(_DATA_REGISTERED):
        return
    websocket_api.async_register_command(hass, websocket_upload_gear_picture)
    websocket_api.async_register_command(hass, websocket_remove_gear_picture)
    hass.data[_DATA_REGISTERED] = True


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
    """Upload or replace a local Gear product picture."""
    slug = slugify_gear_picture_name(msg["name"])
    if not slug:
        connection.send_error(msg["id"], "invalid_name", "Kunde inte skapa bildnamn")
        return

    try:
        extension, data = decode_gear_picture(msg["content"], msg["mime_type"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_picture", str(err))
        return

    try:
        target = await hass.async_add_executor_job(
            write_gear_picture,
            _picture_directory(hass),
            slug,
            extension,
            data,
        )
    except OSError as err:
        connection.send_error(msg["id"], "save_failed", str(err))
        return

    connection.send_result(
        msg["id"],
        {
            "slug": slug,
            "filename": target.name,
            "url": f"/local/gear_pictures/{target.name}",
        },
    )


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
    """Remove local Gear product-picture variants."""
    slug = slugify_gear_picture_name(msg["name"])
    if not slug:
        connection.send_error(msg["id"], "invalid_name", "Kunde inte skapa bildnamn")
        return

    try:
        removed = await hass.async_add_executor_job(
            remove_gear_pictures,
            _picture_directory(hass),
            slug,
        )
    except OSError as err:
        connection.send_error(msg["id"], "remove_failed", str(err))
        return

    connection.send_result(msg["id"], {"slug": slug, "removed": removed})
