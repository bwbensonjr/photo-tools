"""Plan, apply, and verify metadata for scanned JPEG photographs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


FOLDER_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")
JPEG_SUFFIXES = {".jpg", ".jpeg"}
DEFAULT_START = dt.time(12, 0)
DEFAULT_INTERVAL = dt.timedelta(minutes=1)

DATE_TAGS = (
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "EXIF:ModifyDate",
    "XMP-photoshop:DateCreated",
)
DESCRIPTION_TAGS = (
    "EXIF:ImageDescription",
    "IPTC:Caption-Abstract",
    "XMP-dc:Description",
)
TITLE_TAGS = (
    "IPTC:ObjectName",
    "XMP-dc:Title",
    "XMP-photoshop:Headline",
)
KEYWORD_TAGS = (
    "IPTC:Keywords",
    "XMP-dc:Subject",
)
WRITE_TAGS = DATE_TAGS + DESCRIPTION_TAGS + TITLE_TAGS + KEYWORD_TAGS

READ_KEYS = {
    "EXIF:DateTimeOriginal": "EXIF:DateTimeOriginal",
    "EXIF:CreateDate": "EXIF:CreateDate",
    "EXIF:ModifyDate": "EXIF:ModifyDate",
    "XMP-photoshop:DateCreated": "XMP:DateCreated",
    "EXIF:ImageDescription": "EXIF:ImageDescription",
    "IPTC:Caption-Abstract": "IPTC:Caption-Abstract",
    "XMP-dc:Description": "XMP:Description",
    "IPTC:ObjectName": "IPTC:ObjectName",
    "XMP-dc:Title": "XMP:Title",
    "XMP-photoshop:Headline": "XMP:Headline",
    "IPTC:Keywords": "IPTC:Keywords",
    "XMP-dc:Subject": "XMP:Subject",
}

class ScanMetadataError(Exception):
    """A user-facing planning, metadata, or verification error."""


@dataclass(frozen=True)
class PlannedPhoto:
    """One deterministic metadata assignment."""

    root: Path
    folder: Path
    photo: Path
    date: dt.date
    folder_order: int
    photo_order: int
    timestamp: dt.datetime
    description: str


@dataclass(frozen=True)
class Plan:
    """A complete plan plus nonfatal discovery diagnostics."""

    root: Path
    entries: tuple[PlannedPhoto, ...]
    skipped: tuple[str, ...]
    duplicate_date_counts: tuple[tuple[dt.date, int], ...]

    def selected(self, only: set[str]) -> tuple[PlannedPhoto, ...]:
        """Return selected entries after validating requested folder names."""
        available = {entry.folder.name for entry in self.entries}
        missing = sorted(only - available)
        if missing:
            names = ", ".join(missing)
            raise ScanMetadataError(f"unknown or empty folder selection: {names}")
        if not only:
            return self.entries
        return tuple(entry for entry in self.entries if entry.folder.name in only)


@dataclass(frozen=True)
class MetadataSnapshot:
    """ExifTool values read for a photograph."""

    image_data_hash: str
    values: dict[str, object]


def parse_clock(text: str) -> dt.time:
    """Parse an HH:MM or HH:MM:SS clock value."""
    for layout in ("%H:%M", "%H:%M:%S"):
        try:
            return dt.datetime.strptime(text, layout).time()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"expected HH:MM or HH:MM:SS, got {text!r}"
    )


def positive_int(text: str) -> int:
    """Parse a positive integer argument."""
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a positive integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def describe(slug: str) -> str:
    """Turn the folder suffix into a human-readable description."""
    return slug.replace("-", " ").strip()


def _inside(path: Path, root: Path) -> bool:
    """Return whether path is root or one of its descendants."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_root(root: Path) -> Path:
    if root.is_symlink():
        raise ScanMetadataError(f"scan root must not be a symlink: {root}")
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError as error:
        raise ScanMetadataError(f"scan root does not exist: {root}") from error
    if not resolved.is_dir():
        raise ScanMetadataError(f"scan root is not a directory: {root}")
    return resolved


def build_plan(
    root: Path,
    *,
    start: dt.time = DEFAULT_START,
    interval: dt.timedelta = DEFAULT_INTERVAL,
) -> Plan:
    """Discover photographs and assign stable timestamps across each date."""
    if interval <= dt.timedelta(0):
        raise ScanMetadataError("timestamp interval must be positive")

    resolved_root = _resolve_root(root)
    folders: list[tuple[dt.date, Path, str, tuple[Path, ...]]] = []
    skipped: list[str] = []

    for child in sorted(resolved_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            skipped.append(f"{child.name}: hidden directory")
            continue
        if child.is_symlink():
            raise ScanMetadataError(f"scan folder must not be a symlink: {child}")

        match = FOLDER_RE.fullmatch(child.name)
        if not match:
            skipped.append(f"{child.name}: expected YYYY-MM-DD-description")
            continue
        year, month, day, slug = match.groups()
        try:
            folder_date = dt.date(int(year), int(month), int(day))
        except ValueError:
            skipped.append(f"{child.name}: invalid calendar date")
            continue
        description = describe(slug)
        if not description:
            skipped.append(f"{child.name}: empty description")
            continue

        photos: list[Path] = []
        for candidate in sorted(child.iterdir(), key=lambda path: path.name):
            if candidate.suffix.lower() not in JPEG_SUFFIXES:
                continue
            if candidate.is_symlink():
                raise ScanMetadataError(
                    f"photograph must not be a symlink: {candidate}"
                )
            resolved_photo = candidate.resolve(strict=True)
            if not resolved_photo.is_file() or not _inside(resolved_photo, resolved_root):
                raise ScanMetadataError(
                    f"photograph resolves outside the scan root: {candidate}"
                )
            if "\n" in str(resolved_photo) or "\r" in str(resolved_photo):
                raise ScanMetadataError(
                    f"photograph path contains a line break: {candidate}"
                )
            photos.append(resolved_photo)
        if not photos:
            skipped.append(f"{child.name}: no JPEG photographs")
            continue
        folders.append((folder_date, child.resolve(), description, tuple(photos)))

    folders.sort(key=lambda item: (item[0], item[1].name))
    folder_counts = Counter(folder_date for folder_date, _, _, _ in folders)
    duplicate_counts = tuple(
        sorted((date, count) for date, count in folder_counts.items() if count > 1)
    )

    entries: list[PlannedPhoto] = []
    seen: set[Path] = set()
    seen_file_ids: set[tuple[int, int]] = set()
    current_date: dt.date | None = None
    cursor: dt.datetime | None = None
    folder_order = -1
    for folder_date, folder, description, photos in folders:
        if folder_date != current_date:
            current_date = folder_date
            cursor = dt.datetime.combine(folder_date, start)
            folder_order = 0
        else:
            folder_order += 1
        assert cursor is not None
        for photo_order, photo in enumerate(photos):
            if cursor.date() != folder_date:
                raise ScanMetadataError(
                    f"timestamp sequence for {folder_date.isoformat()} crosses midnight"
                )
            if photo in seen:
                raise ScanMetadataError(f"duplicate photograph target: {photo}")
            stat = photo.stat()
            file_id = (stat.st_dev, stat.st_ino)
            if file_id in seen_file_ids:
                raise ScanMetadataError(
                    f"duplicate photograph target (hard link): {photo}"
                )
            seen.add(photo)
            seen_file_ids.add(file_id)
            entries.append(
                PlannedPhoto(
                    root=resolved_root,
                    folder=folder,
                    photo=photo,
                    date=folder_date,
                    folder_order=folder_order,
                    photo_order=photo_order,
                    timestamp=cursor,
                    description=description,
                )
            )
            cursor += interval

    return Plan(
        root=resolved_root,
        entries=tuple(entries),
        skipped=tuple(skipped),
        duplicate_date_counts=duplicate_counts,
    )


def render_plan(plan: Plan, entries: Sequence[PlannedPhoto]) -> str:
    """Render a stable, human-readable dry-run plan."""
    lines: list[str] = []
    if plan.duplicate_date_counts:
        lines.append(
            "same-date groups: "
            + ", ".join(
                f"{date.isoformat()} ({count} folders)"
                for date, count in plan.duplicate_date_counts
            )
        )
    current: Path | None = None
    for entry in entries:
        if entry.folder != current:
            current = entry.folder
            if lines:
                lines.append("")
            lines.append(f'{entry.folder.name} -> "{entry.description}"')
        lines.append(f"  {entry.timestamp:%Y-%m-%d %H:%M:%S}  {entry.photo.name}")
    folders = len({entry.folder for entry in entries})
    lines.append("")
    lines.append(f"dry run: {len(entries)} photos in {folders} folders")
    return "\n".join(lines)


def validate_descriptions(entries: Sequence[PlannedPhoto]) -> None:
    """Validate the strictest legacy IPTC text limit used by the mapping."""
    for description in sorted({entry.description for entry in entries}):
        encoded = description.encode("utf-8")
        if len(encoded) > 64:
            raise ScanMetadataError(
                "description exceeds the 64-byte IPTC ObjectName/Keywords limit: "
                f"{description!r} ({len(encoded)} bytes)"
            )


def exiftool_argfile_lines(entries: Sequence[PlannedPhoto]) -> list[str]:
    """Create one-argument-per-line ExifTool input."""
    validate_descriptions(entries)
    lines = [
        "-charset",
        "filename=UTF8",
        "-charset",
        "IPTC=UTF8",
        "-codedcharacterset=UTF8",
    ]
    for entry in entries:
        when = entry.timestamp.strftime("%Y:%m:%d %H:%M:%S")
        for tag in DATE_TAGS:
            lines.append(f"-{tag}={when}")
        for tag in DESCRIPTION_TAGS + TITLE_TAGS + KEYWORD_TAGS:
            lines.append(f"-{tag}={entry.description}")
        lines.append(str(entry.photo))
        lines.append("-execute")
    return lines


def find_exiftool() -> str:
    """Return the ExifTool executable path or raise a user-facing error."""
    executable = shutil.which("exiftool")
    if executable is None:
        raise ScanMetadataError(
            "ExifTool is required for --apply and verification but was not found"
        )
    return executable


def _run_exiftool(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run ExifTool and translate subprocess failures."""
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        raise ScanMetadataError(f"could not run ExifTool: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise ScanMetadataError(f"ExifTool failed: {detail}")
    return result


def read_metadata(
    entries: Sequence[PlannedPhoto], *, executable: str
) -> dict[Path, MetadataSnapshot]:
    """Read mapped fields and image hashes in one ExifTool JSON operation."""
    if not entries:
        return {}
    command = [executable, "-json", "-G0", "-s", "-ImageDataHash"]
    command.extend(f"-{tag}" for tag in WRITE_TAGS)
    command.extend(str(entry.photo) for entry in entries)
    result = _run_exiftool(command)
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ScanMetadataError("ExifTool returned invalid JSON") from error

    snapshots: dict[Path, MetadataSnapshot] = {}
    for record in records:
        photo = Path(record["SourceFile"]).resolve()
        image_hash = record.get("File:ImageDataHash")
        if not isinstance(image_hash, str) or not image_hash:
            raise ScanMetadataError(f"ExifTool did not return ImageDataHash for {photo}")
        snapshots[photo] = MetadataSnapshot(
            image_data_hash=image_hash,
            values={key: record.get(read_key) for key, read_key in READ_KEYS.items()},
        )
    return snapshots


def apply_metadata(
    entries: Sequence[PlannedPhoto], *, backup: bool, executable: str
) -> None:
    """Apply one validated plan through an ephemeral ExifTool argument file."""
    if not entries:
        raise ScanMetadataError("nothing to apply")
    lines = exiftool_argfile_lines(entries)
    with tempfile.TemporaryDirectory(prefix="photo-tools-") as temp_dir:
        argfile = Path(temp_dir) / "exiftool.args"
        argfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = [executable, "-@", str(argfile), "-common_args"]
        if not backup:
            command.append("-overwrite_original")
        _run_exiftool(command)


def _equal_text(value: object, expected: str) -> bool:
    if isinstance(value, list):
        return value == [expected]
    return value == expected


def verify_metadata(
    entries: Sequence[PlannedPhoto],
    before: dict[Path, MetadataSnapshot],
    after: dict[Path, MetadataSnapshot],
) -> list[str]:
    """Return all metadata or image-payload verification errors."""
    errors: list[str] = []
    for entry in entries:
        prior = before.get(entry.photo)
        current = after.get(entry.photo)
        if prior is None or current is None:
            errors.append(f"{entry.photo}: missing ExifTool verification record")
            continue
        if current.image_data_hash != prior.image_data_hash:
            errors.append(f"{entry.photo}: JPEG image data changed")
        when = entry.timestamp.strftime("%Y:%m:%d %H:%M:%S")
        for tag in DATE_TAGS:
            if current.values.get(tag) != when:
                errors.append(
                    f"{entry.photo}: {tag} expected {when!r}, "
                    f"got {current.values.get(tag)!r}"
                )
        for tag in DESCRIPTION_TAGS + TITLE_TAGS + KEYWORD_TAGS:
            value = current.values.get(tag)
            if not _equal_text(value, entry.description):
                errors.append(
                    f"{entry.photo}: {tag} expected {entry.description!r}, got {value!r}"
                )
    return errors


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="scan root")
    parser.add_argument(
        "--apply", action="store_true", help="write and verify metadata"
    )
    parser.add_argument(
        "--backup", action="store_true", help="retain ExifTool _original files"
    )
    parser.add_argument(
        "--only", action="append", default=[], help="select one folder (repeatable)"
    )
    parser.add_argument(
        "--start",
        type=parse_clock,
        default=DEFAULT_START,
        help="first timestamp for each date (default: 12:00)",
    )
    parser.add_argument(
        "--interval-minutes",
        type=positive_int,
        default=1,
        help="minutes between photographs (default: 1)",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute a parsed command."""
    if args.backup and not args.apply:
        raise ScanMetadataError("--backup requires --apply")
    plan = build_plan(
        args.root,
        start=args.start,
        interval=dt.timedelta(minutes=args.interval_minutes),
    )
    for diagnostic in plan.skipped:
        print(f"skipping {diagnostic}", file=sys.stderr)
    entries = plan.selected(set(args.only))
    if not entries:
        raise ScanMetadataError("nothing to do")
    validate_descriptions(entries)
    if not args.apply:
        print(render_plan(plan, entries))
        print("re-run with --apply to write metadata")
        return 0

    if args.apply:
        executable = find_exiftool()
        before = read_metadata(entries, executable=executable)
        apply_metadata(entries, backup=args.backup, executable=executable)
        after = read_metadata(entries, executable=executable)
        errors = verify_metadata(entries, before, after)
        if errors:
            raise ScanMetadataError("verification failed:\n" + "\n".join(errors))
        print(f"tagged and verified {len(entries)} photos")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ScanMetadataError as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
