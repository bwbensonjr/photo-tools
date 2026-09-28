"""Command-line behavior tests."""

import hashlib
import shutil
from pathlib import Path

import pytest

from photo_tools.scan_metadata import main

from conftest import make_folder, make_jpeg


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dry_run_is_default_and_does_not_change_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = make_folder(
        tmp_path, "1997-03-06-In-the-woods", ["b.jpg", "a.jpg"]
    )
    before = {path: file_hash(path) for path in folder.iterdir()}

    assert main(["--root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert '1997-03-06-In-the-woods -> "In the woods"' in captured.out
    assert captured.out.index("a.jpg") < captured.out.index("b.jpg")
    assert "dry run: 2 photos in 1 folders" in captured.out
    assert "re-run with --apply" in captured.out
    assert {path: file_hash(path) for path in folder.iterdir()} == before


def test_root_is_required() -> None:
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2


@pytest.mark.parametrize("value", ["0", "-1", "nope"])
def test_interval_must_be_positive(value: str, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "--root",
                str(tmp_path),
                "--interval-minutes",
                value,
            ]
        )
    assert raised.value.code == 2


def test_backup_requires_apply(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-Valid", ["a.jpg"])
    with pytest.raises(SystemExit) as raised:
        main(["--root", str(tmp_path), "--backup"])
    assert raised.value.code == 2


def test_only_accepts_repeated_folders(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_folder(tmp_path, "1997-03-06-A", ["a.jpg"])
    make_folder(tmp_path, "1997-03-06-B", ["b.jpg"])

    assert main(["--root", str(tmp_path), "--only", "1997-03-06-B"]) == 0

    output = capsys.readouterr().out
    assert "1997-03-06-B" in output
    assert "1997-03-06-A ->" not in output
    assert "12:01:00" in output


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="ExifTool not installed")
def test_documented_apply_command_uses_a_temporary_copy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "1997-03-06-In-the-woods"
    photo = make_jpeg(folder / "scan.jpg")

    assert main(["--root", str(tmp_path), "--apply", "--backup"]) == 0

    assert photo.with_name(f"{photo.name}_original").exists()
    assert "tagged and verified 1 photos" in capsys.readouterr().out
