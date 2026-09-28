"""ExifTool mapping, application, and verification tests."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

from photo_tools.scan_metadata import (
    DATE_TAGS,
    DESCRIPTION_TAGS,
    KEYWORD_TAGS,
    TITLE_TAGS,
    MetadataSnapshot,
    PlannedPhoto,
    ScanMetadataError,
    apply_metadata,
    build_plan,
    exiftool_argfile_lines,
    read_metadata,
    validate_descriptions,
    verify_metadata,
)

from conftest import make_jpeg


def planned(tmp_path: Path, description: str = "In the woods") -> PlannedPhoto:
    folder = tmp_path / "1997-03-06-In-the-woods"
    photo = folder / "scan.jpg"
    return PlannedPhoto(
        root=tmp_path,
        folder=folder,
        photo=photo,
        date=dt.date(1997, 3, 6),
        folder_order=0,
        photo_order=0,
        timestamp=dt.datetime(1997, 3, 6, 12, 0),
        description=description,
    )


def test_argfile_uses_exact_family_qualified_mapping(tmp_path: Path) -> None:
    entry = planned(tmp_path)

    lines = exiftool_argfile_lines([entry])

    assert lines[:5] == [
        "-charset",
        "filename=UTF8",
        "-charset",
        "IPTC=UTF8",
        "-codedcharacterset=UTF8",
    ]
    assert "-EXIF:DateTimeOriginal=1997:03:06 12:00:00" in lines
    for tag in DATE_TAGS[1:]:
        assert f"-{tag}=1997:03:06 12:00:00" in lines
    for tag in DESCRIPTION_TAGS + TITLE_TAGS + KEYWORD_TAGS:
        assert f"-{tag}=In the woods" in lines
    assert str(entry.photo) in lines
    assert lines[-1] == "-execute"


def test_iptc_boundary_and_unicode_are_accepted(tmp_path: Path) -> None:
    validate_descriptions([planned(tmp_path, "é" * 32)])


def test_iptc_overlength_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScanMetadataError, match="64-byte"):
        validate_descriptions([planned(tmp_path, "é" * 33)])


def test_verify_reports_field_and_image_hash_mismatches(tmp_path: Path) -> None:
    entry = planned(tmp_path)
    before = {
        entry.photo: MetadataSnapshot(image_data_hash="before", values={})
    }
    after = {
        entry.photo: MetadataSnapshot(
            image_data_hash="after",
            values={tag: "wrong" for tag in DATE_TAGS + DESCRIPTION_TAGS + TITLE_TAGS + KEYWORD_TAGS},
        )
    }

    errors = verify_metadata([entry], before, after)

    assert any("JPEG image data changed" in error for error in errors)
    assert any("EXIF:DateTimeOriginal" in error for error in errors)
    assert any("XMP-dc:Description" in error for error in errors)


def test_exiftool_subprocess_error_is_reported(tmp_path: Path) -> None:
    entry = planned(tmp_path)

    with pytest.raises(ScanMetadataError, match="could not run ExifTool"):
        read_metadata([entry], executable=str(tmp_path / "missing-exiftool"))


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="ExifTool not installed")
def test_apply_round_trip_backup_control_and_selected_scope(tmp_path: Path) -> None:
    selected_folder = tmp_path / "1997-03-06-A-selected"
    unselected_folder = tmp_path / "1997-03-06-B-unselected"
    selected = make_jpeg(selected_folder / "a.jpg")
    unselected = make_jpeg(unselected_folder / "b.jpg")
    unselected_before = unselected.read_bytes()
    plan = build_plan(tmp_path)
    entries = plan.selected({selected_folder.name})
    executable = shutil.which("exiftool")
    assert executable is not None

    before = read_metadata(entries, executable=executable)
    apply_metadata(entries, backup=True, executable=executable)
    after = read_metadata(entries, executable=executable)

    assert verify_metadata(entries, before, after) == []
    assert selected.with_name(f"{selected.name}_original").exists()
    assert unselected.read_bytes() == unselected_before
    assert not unselected.with_name(f"{unselected.name}_original").exists()

    backup_path = selected.with_name(f"{selected.name}_original")
    backup_path.unlink()
    before = read_metadata(entries, executable=executable)
    apply_metadata(entries, backup=False, executable=executable)
    after = read_metadata(entries, executable=executable)
    assert verify_metadata(entries, before, after) == []
    assert not backup_path.exists()
