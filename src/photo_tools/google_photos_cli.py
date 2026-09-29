"""Preview or upload deterministic scan folders to a new Google Photos album."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence

from photo_tools.google_photos import (
    AmbiguousRequestError,
    ConfirmedRequestError,
    GooglePhotosClient,
    GooglePhotosError,
    InstalledAppAuthorizer,
    UploadJournal,
    album_manifest_text,
    build_album_plan,
    pending_group_placements,
    render_album_preview,
    upload_album,
)
from photo_tools.scan_metadata import ScanMetadataError, build_plan


DEFAULT_CLIENT_CONFIG = Path("~/.config/photo-tools/google-photos-client.json")


def _journal_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "album"


def default_journal(root: Path, title: str) -> Path:
    """Return the operational-state location stored with the photographs."""
    return root / ".scan-tools" / f"google-photos-{_journal_slug(title)}.json"


def default_client_config() -> Path:
    """Return the conventional private OAuth client configuration path."""
    return DEFAULT_CLIENT_CONFIG.expanduser()


def build_parser() -> argparse.ArgumentParser:
    """Build the safe-by-default Google Photos command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="scan root")
    parser.add_argument("--album-title", required=True, help="new Google album title")
    parser.add_argument(
        "--only", action="append", default=[], help="select one folder (repeatable)"
    )
    parser.add_argument(
        "--manifest", type=Path, help="write the local Markdown album manifest"
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="authorize and create or resume the Google Photos album",
    )
    parser.add_argument(
        "--client-config",
        type=Path,
        help=(
            "installed-app OAuth JSON stored outside this repository "
            "(default: ~/.config/photo-tools/google-photos-client.json)"
        ),
    )
    parser.add_argument(
        "--journal",
        type=Path,
        help="upload journal (default: ROOT/.scan-tools/google-photos-TITLE.json)",
    )
    parser.add_argument(
        "--resolve-uncertain",
        choices=("completed", "pending"),
        help="resolve the journal's inspected uncertain operation before resuming",
    )
    parser.add_argument(
        "--resolved-id",
        action="append",
        default=[],
        help="remote ID for a completed uncertain operation (repeatable)",
    )
    parser.add_argument(
        "--resolved-url",
        default="",
        help="album URL when resolving uncertain album creation as completed",
    )
    return parser


def _progress_text(journal: UploadJournal, *, failed: str = "none") -> str:
    confirmed_headings = len(journal.data["confirmed_headings"])
    confirmed_media = len(journal.data["confirmed_media"])
    total_headings = len(journal.plan.groups)
    total_media = journal.plan.photo_count
    uncertain = journal.uncertain
    uncertain_text = "none" if uncertain is None else str(uncertain.get("kind", "unknown"))
    return (
        f"confirmed: {confirmed_headings}/{total_headings} headings, "
        f"{confirmed_media}/{total_media} photos; failed: {failed}; "
        f"uncertain: {uncertain_text}; unattempted: "
        f"{total_headings - confirmed_headings} headings, "
        f"{total_media - confirmed_media} photos"
    )


def run(
    args: argparse.Namespace,
    *,
    authorizer: InstalledAppAuthorizer | None = None,
) -> int:
    """Execute a parsed preview or upload command."""
    if args.client_config is not None and not args.upload:
        raise GooglePhotosError("--client-config requires --upload")
    if args.resolve_uncertain is not None and not args.upload:
        raise GooglePhotosError("--resolve-uncertain requires --upload")
    if (args.resolved_id or args.resolved_url) and args.resolve_uncertain is None:
        raise GooglePhotosError(
            "--resolved-id and --resolved-url require --resolve-uncertain"
        )
    scan_plan = build_plan(args.root)
    entries = scan_plan.selected(set(args.only))
    if not entries:
        raise GooglePhotosError("nothing to preview or upload")
    album_plan = build_album_plan(scan_plan, entries, title=args.album_title)

    print(render_album_preview(album_plan))
    if args.manifest is not None:
        args.manifest.write_text(album_manifest_text(album_plan), encoding="utf-8")
        print(f"wrote Google Photos manifest: {args.manifest}")
    if not args.upload:
        print("re-run with --upload to contact Google Photos")
        return 0

    journal_path = args.journal or default_journal(album_plan.root, album_plan.title)
    journal = UploadJournal.open_or_create(journal_path, album_plan)
    if args.resolve_uncertain is not None:
        journal.resolve_uncertain(
            args.resolve_uncertain,
            remote_ids=args.resolved_id,
            product_url=args.resolved_url,
        )
        print(f"resolved uncertain operation as {args.resolve_uncertain}")
    print(f"upload state: {_progress_text(journal)}")
    for folder_name, placement in pending_group_placements(album_plan, journal):
        print(f"pending placement: {folder_name} -> {placement}")

    oauth = authorizer or InstalledAppAuthorizer()
    client_config = args.client_config or default_client_config()
    transport = oauth.authorized_transport(client_config)
    client = GooglePhotosClient(transport)
    try:
        album_url = upload_album(
            album_plan,
            journal,
            client,
            on_folder_start=lambda folder_name: print(
                f"uploading folder: {folder_name}"
            ),
        )
    except ConfirmedRequestError as error:
        raise GooglePhotosError(
            f"{error}\n{_progress_text(journal, failed='confirmed request failure')}"
        ) from error
    except AmbiguousRequestError as error:
        raise GooglePhotosError(f"{error}\n{_progress_text(journal)}") from error

    print(_progress_text(journal))
    print(f"album ready: {album_url}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (GooglePhotosError, ScanMetadataError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
