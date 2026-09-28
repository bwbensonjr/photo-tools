# Tasks

## 1. Python Project and Command-Line Shell

- [x] 1.1 Add a `uv`-managed `pyproject.toml`, `src/photo_tools` package, `scan-metadata` console entry point, and pytest development dependency; verify `uv sync` and `uv run scan-metadata --help` succeed.
- [x] 1.2 Implement argument parsing for required `--root`, dry-run default, `--apply`, `--backup`, repeated `--only`, `--start`, positive interval, and manifest output; verify CLI tests cover defaults, invalid values, and mutually incompatible options.

## 2. Discovery and Deterministic Planning

- [x] 2.1 Implement immutable plan records and top-level folder/JPEG discovery with date and description parsing; verify unit tests cover valid folders, empty folders, invalid dates, unsupported entries, mixed-case JPEG suffixes, and non-recursive behavior.
- [x] 2.2 Implement complete-date grouping, folder-name ordering, filename ordering, and continuous timestamp allocation; verify tests model the three 1997-03-06 folder sizes and assert unique, contiguous, non-interleaved ranges.
- [x] 2.3 Apply `--only` after complete planning and reject unknown selections, symlinks or targets outside the root, duplicates, non-positive intervals, and midnight overflow; verify targeted tests prove a selected folder receives the same timestamps in filtered and unfiltered runs.
- [x] 2.4 Render the dry-run plan and skip diagnostics without invoking ExifTool writes; verify a CLI integration test snapshots the ordered output and confirms fixture file hashes remain unchanged.
- [x] 2.5 Document folder naming, deterministic alphabetical folder ordering, scan filename ordering, start/interval limits, and dry-run review in `README.md`; verify every documented planning command runs successfully against temporary fixtures.

## 3. ExifTool Application and Verification

- [x] 3.1 Implement ExifTool availability checks, temporary argument-file generation, and the centralized EXIF/IPTC/XMP mapping from `design.md`; verify unit tests assert the exact family-qualified tags and UTF-8 values passed for representative plan entries.
- [x] 3.2 Preflight IPTC encoding and length constraints and refuse invalid metadata before any write; verify tests cover boundary-length, overlength, and non-ASCII descriptions without silent truncation.
- [x] 3.3 Implement explicit application with selected-folder scoping and backup retention control; verify integration tests apply to temporary JPEG copies, create `_original` files only when requested, and leave unselected files byte-for-byte unchanged.
- [x] 3.4 Read all required fields and `ImageDataHash` before and after writes, compare them with the plan, and return detailed nonzero failures; verify integration tests cover a successful round trip, unchanged image data, a forced field mismatch, and an ExifTool subprocess error.
- [x] 3.5 Document ExifTool installation expectations, safe first-run backup usage, verification output, partial-failure recovery, and the requirement to tag before importing into Photos; verify the documented apply example succeeds on a temporary copy and never targets the real scan root.

## 4. Google Photos Album Workflow

- [x] 4.1 Remove the unsupported macOS Shortcut posting options, subprocess adapter, setup guide, and primary-workflow claims while retaining accurate Apple Photos metadata and sharing guidance; verify tests and documentation contain no claim that macOS Photos supplies `Post to Shared Album`.
- [x] 4.2 Generalize the existing manifest into a deterministic Google album preview containing the destination title, dated folder headings, ordered filenames, and exact native descriptions; verify tests cover duplicate-date groups and filtered output without network access.
- [x] 4.3 Add the minimum Google OAuth and HTTP dependencies through `uv`, an installed-application authorization adapter, operating-system credential storage, and diagnostic redaction; verify fake-credential tests prove no client secret or token reaches repository files, journals, or output.
- [x] 4.4 Add a `google-photos-upload` console command with required root and album title, repeated folder filters, local preview default, explicit `--upload`, external client-configuration selection, and journal selection; verify CLI tests cover safe defaults and invalid option combinations without OAuth or HTTP calls.
- [x] 4.5 Implement creation and discovery of the application's destination album plus Original-quality byte upload and ordered media-item creation with filename and native description; verify fake-transport tests cover the two-stage protocol, API batching, description values, app-created-content restrictions, and the 20,000-item preflight.
- [x] 4.6 Add one dated text enrichment before every folder batch and preserve deterministic folder and filename order through remote creation; verify request-order tests model multiple same-date folders and assert contiguous headings and items.
- [x] 4.7 Implement a versioned, non-secret upload journal with source identity, hashes, album ID and URL, confirmed headings and media items, and uncertain operations; verify resume tests skip confirmed work, reject changed source files, and stop at unresolved ambiguity without duplicate requests.
- [x] 4.8 Add bounded retry only for confirmed pre-acceptance transient failures and precise reporting for confirmed, failed, uncertain, and unattempted work; verify tests cover rate limits, server errors, timeouts, interruption, redaction, and no automatic retry after an ambiguous create request.
- [x] 4.9 Document Google Cloud OAuth setup, Original-quality storage costs, application-created album constraints, the one-time manual sharing checklist, link and collaboration risks, and why repository commands are used instead of an agent skill; verify every non-uploading documented command runs against temporary fixtures.
- [x] 4.10 Execute an end-to-end acceptance test with two disposable tagged fixture folders and a temporary application-created Google Photos album; record platform and API details, confirm both headings and both native descriptions from a second viewing context, enable sharing manually, and verify local hashes remain unchanged.

## 5. Migration and Integration Checks

- [x] 5.1 Compare the new and legacy dry-run plans on representative single-date folders and all six duplicate-date groups without applying writes; verify single-folder order/metadata equivalence and confirm every duplicate-date group has unique timestamps.
- [x] 5.2 Document migration from `Scans/.scan-tools/tag_scans.py`, including that the legacy script and generated argument file remain untouched until separate cleanup is authorized; verify `git status` contains no photograph or `.scan-tools` changes.
- [x] 5.3 Run the complete test suite and a read-only dry run against `/Users/bwb/Pictures/Scans`; verify `uv run pytest` passes, the run reports the expected six duplicate-date groups without timestamp collisions, and pre/post hashes confirm the real photographs were not modified.
- [x] 5.4 Run the revised test suite plus a local-only Google album preview against `/Users/bwb/Pictures/Scans`; verify tests pass, preview output contains all six duplicate-date groups with headings and descriptions in deterministic order, no OAuth or Google request occurs, and pre/post photograph hashes match.
