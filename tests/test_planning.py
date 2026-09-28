"""Tests for scan discovery and deterministic planning."""

import datetime as dt
from pathlib import Path

import pytest

from photo_tools.scan_metadata import ScanMetadataError, build_plan, describe

from conftest import make_folder


def names(count: int, prefix: str = "scan") -> list[str]:
    return [f"{prefix}_{index:03}.jpg" for index in range(count)]


def test_discovers_direct_jpegs_and_reports_unsupported_folders(tmp_path: Path) -> None:
    valid = make_folder(
        tmp_path,
        "1997-03-06-In-the-woods",
        ["b.JPEG", "a.jpg", "notes.txt"],
    )
    nested = valid / "nested"
    nested.mkdir()
    (nested / "ignored.jpg").write_bytes(b"nested")
    make_folder(tmp_path, "1997-02-31-Impossible", ["a.jpg"])
    make_folder(tmp_path, "To-Sort", ["a.jpg"])
    (tmp_path / "1998-01-01-Empty").mkdir()

    plan = build_plan(tmp_path)

    assert [entry.photo.name for entry in plan.entries] == ["a.jpg", "b.JPEG"]
    assert {entry.description for entry in plan.entries} == {"In the woods"}
    assert len(plan.skipped) == 3
    assert any("invalid calendar date" in item for item in plan.skipped)
    assert any("expected YYYY-MM-DD-description" in item for item in plan.skipped)
    assert any("no JPEG photographs" in item for item in plan.skipped)


def test_description_replaces_hyphens() -> None:
    assert describe("In-the-woods") == "In the woods"


def test_three_same_date_folders_receive_contiguous_unique_ranges(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-03-06-Hannah-Maya", names(25, "a"))
    make_folder(tmp_path, "1997-03-06-In-the-woods", names(24, "b"))
    make_folder(tmp_path, "1997-03-06-Mayas-Baptism", names(25, "c"))

    plan = build_plan(tmp_path)

    assert len(plan.entries) == 74
    assert len({entry.timestamp for entry in plan.entries}) == 74
    by_folder: dict[str, list[dt.datetime]] = {}
    for entry in plan.entries:
        by_folder.setdefault(entry.folder.name, []).append(entry.timestamp)
    assert by_folder["1997-03-06-Hannah-Maya"][0].time() == dt.time(12, 0)
    assert by_folder["1997-03-06-Hannah-Maya"][-1].time() == dt.time(12, 24)
    assert by_folder["1997-03-06-In-the-woods"][0].time() == dt.time(12, 25)
    assert by_folder["1997-03-06-In-the-woods"][-1].time() == dt.time(12, 48)
    assert by_folder["1997-03-06-Mayas-Baptism"][0].time() == dt.time(12, 49)
    assert by_folder["1997-03-06-Mayas-Baptism"][-1].time() == dt.time(13, 13)
    assert plan.duplicate_date_counts == ((dt.date(1997, 3, 6), 3),)


def test_filtering_happens_after_complete_date_planning(tmp_path: Path) -> None:
    first = "1997-03-06-A-first"
    second = "1997-03-06-B-second"
    make_folder(tmp_path, first, names(2, "a"))
    make_folder(tmp_path, second, names(2, "b"))
    plan = build_plan(tmp_path)

    filtered = plan.selected({second})
    unfiltered = tuple(entry for entry in plan.entries if entry.folder.name == second)

    assert filtered == unfiltered
    assert filtered[0].timestamp.time() == dt.time(12, 2)


def test_unknown_selection_is_rejected(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-Valid", ["a.jpg"])
    plan = build_plan(tmp_path)

    with pytest.raises(ScanMetadataError, match="unknown or empty"):
        plan.selected({"missing"})


def test_midnight_overflow_is_rejected(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-Too-late", ["a.jpg", "b.jpg"])

    with pytest.raises(ScanMetadataError, match="crosses midnight"):
        build_plan(tmp_path, start=dt.time(23, 59))


def test_nonpositive_interval_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScanMetadataError, match="must be positive"):
        build_plan(tmp_path, interval=dt.timedelta(0))


def test_photo_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jpg"
    outside.write_bytes(b"outside")
    folder = tmp_path / "1997-03-06-Link"
    folder.mkdir()
    (folder / "a.jpg").symlink_to(outside)

    with pytest.raises(ScanMetadataError, match="must not be a symlink"):
        build_plan(tmp_path)


def test_duplicate_hard_link_target_is_rejected(tmp_path: Path) -> None:
    first = make_folder(tmp_path, "1997-03-06-A", ["a.jpg"]) / "a.jpg"
    second_folder = tmp_path / "1997-03-06-B"
    second_folder.mkdir()
    second = second_folder / "b.jpg"
    second.hardlink_to(first)

    with pytest.raises(ScanMetadataError, match="hard link"):
        build_plan(tmp_path)
