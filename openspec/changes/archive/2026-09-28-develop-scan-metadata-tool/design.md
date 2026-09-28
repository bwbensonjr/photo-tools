# Design

## Context

See `proposal.md` for motivation and the three capability specs for observable behavior.

The repository now contains a `uv`-managed Python package and a tested scan planner derived from `/Users/bwb/Pictures/Scans/.scan-tools/tag_scans.py`. The planner fixes six known duplicate-date groups by assigning unique timestamps continuously across sorted folders. Existing JPEGs use explicit EXIF, IPTC, and XMP date, description, title, and keyword mappings and remain the archival source of truth.

Apple Photos imports the embedded caption fields, but its Shared Albums expose separate comments and macOS 26 does not provide the assumed `Post to Shared Album` Shortcut action. Accessibility-based Photos automation would be version-specific and fragile. A manually uploaded Google Photos fixture retains the embedded description under Other but does not promote it into Google Photos' native Description field.

The Google Photos Library API can create albums, upload original media, assign a native description, and add album text enrichments. Since March 31, 2025 it can manage only content created by the application and cannot enable album sharing. Those constraints shape the supported workflow.

## Goals / Non-Goals

**Goals:**

- Reuse the deterministic scan plan for both metadata application and Google album construction.
- Create a prominent native Google Photos description for every photograph.
- Make each scan folder visibly distinct in the album with a dated text heading and contiguous ordered photographs.
- Keep preview free of network and OAuth side effects and make upload explicit.
- Preserve enough non-secret state to resume confirmed incomplete work without silently duplicating uncertain uploads.
- Keep credentials outside the repository and photograph metadata.
- Make the operational workflow runnable and testable without an AI agent.

**Non-Goals:**

- Upload into or manage a Google Photos album created outside this application.
- Enable link sharing, invite people, or configure collaboration, comments, or likes through the API.
- Treat Google Photos as the only archival copy or rely on Google descriptions to round-trip into downloaded JPEG metadata.
- Create an agent skill for routine operation; a skill can be reconsidered later only for recurring guided setup or troubleshooting.
- Automate Apple Photos with mouse, keyboard, accessibility scripting, or a nonexistent Shortcut action.
- Infer dates or descriptions from image content, rename files, recurse into nested directories, or support non-JPEG formats in the first version.
- Delete the existing `.scan-tools` files or modify the scan collection during implementation or automated tests.

## Decisions

### Keep the `src`-layout Python package and separate metadata from upload commands

Retain `scan-metadata` for discovery, planning, metadata application, verification, and local manifests. Add a dedicated `google-photos-upload` console command in the same `photo_tools` package. The upload command imports the same immutable planner and filter logic rather than parsing folders independently.

Separating commands prevents OAuth and networking dependencies from affecting metadata-only runs, keeps upload authorization visibly distinct from in-place metadata mutation, and avoids a breaking rewrite of the working `scan-metadata` interface. A single command with many mutually dependent flags was considered but would make safe defaults and recovery harder to understand.

### Use repository commands rather than an agent skill

The supported workflow is ordinary version-controlled Python with deterministic inputs, explicit CLI options, automated tests, and documented OAuth setup. It must be usable from a terminal, scheduled process, or future UI without Codex. An agent skill would add procedural prompting around the same commands without improving upload correctness, authentication security, or recovery.

If onboarding later proves difficult, a small guidance skill may be added separately to invoke and explain the stable commands. It must not contain credentials, reimplement upload logic, or become the only supported interface.

### Build the complete scan plan before filtering

Discovery parses all valid top-level folders, groups them by calendar date, sorts each group by folder name, and sorts each folder's JPEGs by complete filename. Each date group receives one continuous timestamp sequence. Repeated folder filters select from this completed plan so a photograph's timestamp and relative order remain stable in metadata, previews, manifests, and Google albums.

### Keep the metadata mapping explicit and verifiable

The ExifTool adapter continues to write:

- Capture time: `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `EXIF:ModifyDate`, and `XMP-photoshop:DateCreated`.
- Caption/description: `EXIF:ImageDescription`, `IPTC:Caption-Abstract`, and `XMP-dc:Description`.
- Title/headline: `IPTC:ObjectName`, `XMP-dc:Title`, and `XMP-photoshop:Headline`.
- Keyword: `IPTC:Keywords` and `XMP-dc:Subject`.

Application preflights legacy IPTC constraints, uses a temporary ExifTool argument file, reads required fields back, and verifies `ImageDataHash`. Google upload never replaces these embedded fields; it adds Google-managed presentation metadata.

### Use the Google Photos Library API only for application-created content

The upload command creates a new album from a required title, records its stable ID and product URL, and manages only that album and media uploaded by this application. It requests the minimum current scopes needed to append content and read or edit application-created data. It does not accept a manually created album as a target because the post-2025 API cannot reliably manage it.

Each file follows Google's two-stage protocol: upload bytes to obtain a short-lived token, then create the media item in the application-created album. Creation supplies the complete filename and the exact folder-derived Google Photos description. Requests are batched within Google's limits while preserving source order; confirmed media IDs are written to the journal after each successful response.

Uploads use Google's Original-quality API behavior. The documentation warns that the authenticated account pays the Google storage cost, albums are limited to 20,000 items, and Google Photos remains a presentation and sharing copy rather than the archival master.

### Add a visible text enrichment before each folder batch

For each selected folder, append one text enrichment containing the date and human-readable folder description, then append that folder's media items in filename order. Processing folders serially keeps the heading and photographs contiguous. The per-photo native description duplicates the human meaning intentionally: headings support album browsing, while descriptions remain visible when a photograph is opened or accessed outside its group context.

### Make preview local and upload explicit

Without `--upload`, `google-photos-upload` resolves the complete plan, applies folder filters, validates the proposed album size and description lengths, and prints the album title, each heading, and every ordered filename and description. It performs no OAuth discovery, HTTP request, album creation, or journal mutation.

`--upload` requires an album title, an explicit OAuth client configuration path outside the repository, and a journal path. The default journal location is beneath the scan root's `.scan-tools` directory so operational state stays with the photographs, but the user can override it. The journal contains no credentials.

### Store OAuth tokens outside source control

Use Google's installed-application OAuth flow. The client configuration is supplied by path or environment configuration and is never copied into the repository. Refresh tokens are stored in the operating system credential store; access tokens remain in memory. Diagnostics redact authorization headers, tokens, client values, and sensitive response bodies. Automated tests replace both credential and HTTP adapters.

A plaintext token beside the upload journal was rejected because photograph backups and repository diagnostics should not become credential backups.

### Journal progress and stop on ambiguity

Before the first remote mutation, write a versioned journal containing the album title, source-root identity, complete ordered plan, file sizes and content hashes, and no remote credentials. Record the album ID and URL after creation, then record each confirmed heading and media item after Google acknowledges it.

Transient failures that are known to occur before Google accepts an operation may use bounded exponential backoff. A timeout or interruption after an upload token or create request may have been accepted is ambiguous; record the operation as uncertain and stop. Resume skips only confirmed work and refuses to cross an uncertain entry until the user inspects Google Photos and explicitly marks it completed or pending. This favors duplicate prevention over unattended completion.

### Keep sharing a one-time manual handoff

The Google Photos API no longer offers the sharing scope needed to publish an album. After all planned content is confirmed, print the product URL and a short checklist for choosing direct recipients or link sharing and for configuring collaboration, comments, and likes. This is one manual action per completed album rather than one description action per folder or photograph.

### Test local behavior and validate Google behavior separately

Automated tests use generated JPEG fixtures, a fake credential store, a fake HTTP transport, deterministic retry behavior, and temporary journals. They cover album creation, upload token handling, batching, descriptions, text enrichments, ordering, filtering, resumption, ambiguous failure, redaction, and unchanged local hashes without reaching Google.

A documented manual acceptance test uploads two disposable folders with distinct descriptions to a temporary application-created album, confirms both visible headings and native descriptions in Google Photos, verifies local hashes, enables sharing manually, and checks the view from a second account or private browser context.

## Risks / Trade-offs

- [Google may change the Library API or OAuth scopes] -> Isolate the API adapter, pin tested dependencies, link current official documentation, and fail preflight before creating an album when required capabilities are unavailable.
- [Descriptions created in Google Photos may not be embedded in downloaded JPEGs] -> Keep EXIF, IPTC, and XMP metadata in the local originals and state explicitly that Google Photos is not the archival source of truth.
- [An interrupted create request may produce a duplicate on retry] -> Journal every confirmed response, stop on ambiguous outcomes, and require inspection before resuming uncertain work.
- [Album headings and item order could drift if operations run concurrently] -> Process folders serially and constrain concurrency to byte upload preparation that cannot reorder remote create operations.
- [OAuth credentials could leak through files or logs] -> Use the operating system credential store, keep client configuration outside the repository, redact diagnostics, and test for secret absence.
- [Original-quality uploads consume Google storage] -> Estimate source bytes during preview, document Google One implications, and require user review before upload.
- [Application-created content cannot be merged automatically into an existing manual album] -> Create a new destination album and make the limitation visible before authorization.
- [A shared link can be forwarded] -> Leave sharing disabled by default and document direct-recipient, collaboration, comment, and link-reset controls.
- [Folder-name order may not match intended envelope order] -> Make ordering prominent in preview output and retain a future explicit-order extension point.
- [ExifTool can partially update a batch before a later failure] -> Keep optional backups, verify every selected file, report partial failure precisely, and make reruns deterministic.

## Migration Plan

1. Preserve the completed metadata planner, ExifTool adapter, verification tests, and real-scan read-only checks.
2. Remove the unsupported Shortcut posting path, its setup guide, and claims that macOS supplies a built-in `Post to Shared Album` action; retain accurate Apple Photos metadata and sharing guidance.
3. Add the Google OAuth and HTTP dependencies, credential abstraction, album plan rendering, and fake-transport tests without contacting Google.
4. Add album creation, native descriptions, text enrichments, ordered upload, journaled recovery, and documentation.
5. Run the complete automated suite and a non-networking Google album preview against `/Users/bwb/Pictures/Scans`; verify the six duplicate-date groups remain deterministic and source hashes do not change.
6. Create a temporary Google Photos album through the command and upload two disposable fixture folders. Confirm headings, descriptions, ordering, sharing handoff, and unchanged source hashes.
7. Only after explicit user invocation, apply metadata to selected real folders with backups enabled for the first production run, verify it, preview the production album, and upload a small selected set.
8. Mark `Scans/.scan-tools/tag_scans.py` as superseded in documentation while preserving it and its generated argument file until the user separately authorizes cleanup.

Rollback for metadata uses ExifTool `_original` files or the user's photograph backup. Google upload rollback is manual deletion of the application-created test or production album after reviewing the journal; local originals remain unchanged.
