# Proposal

## Why

The current scan-tagging script assigns every folder on a date the same starting time, so photographs from separate envelopes collide and become interleaved in photo applications. The collection also needs a scalable way to publish large ordered sets with obvious descriptions: Apple Photos Shared Albums do not promote embedded captions into visible comments, macOS does not expose the planned posting action, and ordinary Google Photos uploads show the embedded text only under Other instead of in the prominent description field.

## What Changes

- Add a repository-managed Python command-line tool, packaged with `uv` and `pyproject.toml`, based on the existing `.scan-tools/tag_scans.py` behavior.
- Discover valid `YYYY-MM-DD-description` folders and JPEG files, preserve filename scan order within each folder, and produce clear diagnostics for unsupported folders or files.
- Allocate one deterministic, non-overlapping timestamp sequence across every folder that shares a date, while keeping each folder's photographs contiguous.
- Derive a human-readable description from the folder suffix and write a documented set of EXIF, IPTC, and XMP date, caption, title, and keyword fields compatible with import into Apple Photos and other metadata-aware applications.
- Retain dry-run-first operation, explicit in-place application, optional ExifTool backups, folder filtering, and post-write verification.
- Document Apple Photos caption behavior, the Shared Album comment limitation, and iCloud Shared Photo Library as an alternative for a small trusted Apple-only group.
- Add a repository command that creates an application-owned Google Photos album and uploads selected scan folders in deterministic order.
- Set Google Photos' native per-photo description to the exact folder-derived text and add a visible text heading before each folder group so descriptions are not confined to embedded metadata shown under Other.
- Require an explicit upload option, keep OAuth credentials outside the repository, record resumable upload state with the photographs, and stop safely after ambiguous failures without duplicating completed uploads.
- Leave album sharing as a one-time manual Google Photos action because the Google Photos API no longer permits applications to enable sharing.
- Retain a deterministic upload manifest as an audit artifact and offline review of the album structure.
- Implement the workflow as tested repository commands, not as an agent skill, so it runs independently of Codex and has reproducible security and failure behavior.
- Add automated tests using temporary fixture copies and fake Google transports; the repository test suite must never modify the user's photograph collection or contact Google services.
- Document migration from the script and generated argument file currently stored in `Scans/.scan-tools` without treating generated data as source code.

## Capabilities

### New Capabilities

- `scan-metadata-tagging`: Plan, apply, and verify deterministic date, ordering, description, and keyword metadata for date-named scan folders.
- `apple-photos-sharing-support`: Validate Apple Photos caption imports and accurately document the limitations and alternatives for Apple Photos sharing.
- `google-photos-album-sharing`: Create an ordered Google Photos album with native per-photo descriptions, visible folder headings, recoverable uploads, and a manual sharing handoff.

### Modified Capabilities

None.

## Impact

- Adds Python source, runtime dependencies for Google OAuth and HTTPS access, `pyproject.toml` configuration, tests, and user documentation to this repository.
- Uses the installed ExifTool executable for metadata writes and verification; Python dependencies and commands are managed with `uv`.
- Replaces the operational role of `/Users/bwb/Pictures/Scans/.scan-tools/tag_scans.py`; existing photographs and metadata remain external user data and are not copied into the repository.
- Replaces the unsupported macOS Shortcut posting path with a Google Photos Library API integration limited to albums and media created by this application.
- Adds Google Account authorization, Original-quality storage consumption, application-created album limits, and a one-time manual sharing step as external operational concerns.
- Stores no Google client credentials or refresh tokens in source control. A non-secret upload journal is stored with the photograph collection so interrupted uploads can be reviewed and resumed.
- In-place metadata writes and external uploads remain opt-in and are limited to selected JPEG files beneath an explicitly resolved scan root.
