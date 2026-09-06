"""Tests for reusable local card-picture helpers."""

import base64
from pathlib import Path

import pytest

from custom_components.garmin_connect.gear_picture import (
    decode_gear_picture,
    decode_picture,
    remove_gear_pictures,
    remove_pictures,
    slugify_gear_picture_name,
    slugify_picture_name,
    validate_picture_collection,
    write_gear_picture,
    write_picture,
)


def test_slugify_picture_name() -> None:
    assert slugify_picture_name("Bianchi Impulso Comp") == "bianchi_impulso_comp"
    assert slugify_picture_name("fēnix 7 Pro Sapphire Solar") == "fenix_7_pro_sapphire_solar"
    assert slugify_picture_name("sensor.device_maintenance_Withings") == (
        "sensor_device_maintenance_withings"
    )


def test_gear_slug_alias_stays_compatible() -> None:
    assert slugify_gear_picture_name("Abilica Viktväst 1-10kg") == (
        "abilica_viktvast_1_10kg"
    )


def test_validate_picture_collection() -> None:
    assert validate_picture_collection("device_maintenance") == "device_maintenance"
    assert validate_picture_collection("Garmin-Gear") == "garmin-gear"


@pytest.mark.parametrize("value", ["", "../www", "bad/path", "with space", "åäö"])
def test_validate_picture_collection_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="Collection"):
        validate_picture_collection(value)


def test_decode_jpeg_picture() -> None:
    raw = b"\xff\xd8\xff" + b"garmin-gear"
    extension, decoded = decode_picture(
        base64.b64encode(raw).decode(),
        "image/jpeg",
    )
    assert extension == "jpeg"
    assert decoded == raw


def test_decode_gear_picture_alias() -> None:
    raw = b"\x89PNG\r\n\x1a\n" + b"card-picture"
    extension, decoded = decode_gear_picture(
        base64.b64encode(raw).decode(),
        "image/png",
    )
    assert extension == "png"
    assert decoded == raw


def test_decode_picture_rejects_mismatched_content() -> None:
    raw = b"not-a-png"
    with pytest.raises(ValueError, match="matchar inte"):
        decode_picture(base64.b64encode(raw).decode(), "image/png")


def test_write_picture_removes_stale_extension(tmp_path: Path) -> None:
    stale = tmp_path / "nike_pegasus.jpg"
    stale.write_bytes(b"old")
    target = write_picture(
        tmp_path,
        "nike_pegasus",
        "jpeg",
        b"\xff\xd8\xffnew",
    )
    assert target.name == "nike_pegasus.jpeg"
    assert target.read_bytes() == b"\xff\xd8\xffnew"
    assert not stale.exists()


def test_gear_writer_alias(tmp_path: Path) -> None:
    target = write_gear_picture(
        tmp_path,
        "fenix_7_pro",
        "jpeg",
        b"\xff\xd8\xffnew",
    )
    assert target.name == "fenix_7_pro.jpeg"


def test_remove_picture_variants(tmp_path: Path) -> None:
    for extension in ("jpeg", "png"):
        (tmp_path / f"withings_body_comp.{extension}").write_bytes(b"x")
    removed = remove_pictures(tmp_path, "withings_body_comp")
    assert sorted(removed) == [
        "withings_body_comp.jpeg",
        "withings_body_comp.png",
    ]
    assert list(tmp_path.iterdir()) == []


def test_remove_gear_picture_alias(tmp_path: Path) -> None:
    target = tmp_path / "bontrager_ion_200_rt_flare.webp"
    target.write_bytes(b"x")
    removed = remove_gear_pictures(tmp_path, "bontrager_ion_200_rt_flare")
    assert removed == ["bontrager_ion_200_rt_flare.webp"]
    assert list(tmp_path.iterdir()) == []
