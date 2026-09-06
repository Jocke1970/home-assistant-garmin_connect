"""Tests for local Garmin Gear product-picture helpers."""

import base64
from pathlib import Path

import pytest

from custom_components.garmin_connect.gear_picture import (
    decode_gear_picture,
    remove_gear_pictures,
    slugify_gear_picture_name,
    write_gear_picture,
)


def test_slugify_gear_picture_name() -> None:
    assert slugify_gear_picture_name("Bianchi Impulso Comp") == "bianchi_impulso_comp"
    assert slugify_gear_picture_name("fēnix 7 Pro Sapphire Solar") == "fenix_7_pro_sapphire_solar"
    assert slugify_gear_picture_name("Abilica Viktväst 1-10kg") == "abilica_viktvast_1_10kg"


def test_decode_jpeg_picture() -> None:
    raw = b"\xff\xd8\xff" + b"garmin-gear"
    extension, decoded = decode_gear_picture(
        base64.b64encode(raw).decode(),
        "image/jpeg",
    )
    assert extension == "jpeg"
    assert decoded == raw


def test_decode_picture_rejects_mismatched_content() -> None:
    raw = b"not-a-png"
    with pytest.raises(ValueError, match="matchar inte"):
        decode_gear_picture(base64.b64encode(raw).decode(), "image/png")


def test_write_picture_removes_stale_extension(tmp_path: Path) -> None:
    stale = tmp_path / "nike_pegasus.jpg"
    stale.write_bytes(b"old")
    target = write_gear_picture(
        tmp_path,
        "nike_pegasus",
        "jpeg",
        b"\xff\xd8\xffnew",
    )
    assert target.name == "nike_pegasus.jpeg"
    assert target.read_bytes() == b"\xff\xd8\xffnew"
    assert not stale.exists()


def test_remove_picture_variants(tmp_path: Path) -> None:
    for extension in ("jpeg", "png"):
        (tmp_path / f"bontrager_ion_200_rt_flare.{extension}").write_bytes(b"x")
    removed = remove_gear_pictures(tmp_path, "bontrager_ion_200_rt_flare")
    assert sorted(removed) == [
        "bontrager_ion_200_rt_flare.jpeg",
        "bontrager_ion_200_rt_flare.png",
    ]
    assert list(tmp_path.iterdir()) == []
