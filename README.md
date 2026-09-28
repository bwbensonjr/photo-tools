# Photo Tools

Tools for organizing and tagging scanned family photographs.

## Scan folder layout

Each envelope of print scans lives directly below one scan root. Folder names use an estimated date followed by a description:

```text
Scans/
  1997-03-06-Hannah-Maya/
  1997-03-06-In-the-woods/
  1997-03-06-Mayas-Baptism/
```

`scan-metadata` recognizes `.jpg` and `.jpeg` files directly inside folders named `YYYY-MM-DD-description`. It does not recurse into nested folders or modify unsupported entries.

The planner uses deterministic order:

1. Dates are chronological.
2. Folders sharing a date are alphabetical by complete folder name.
3. Photographs in each folder are alphabetical by complete filename, preserving scanner sequence names.
4. The first photograph for each date defaults to 12:00. Each later photograph advances one minute continuously across every folder on that date.

Because the complete same-date group is planned before `--only` is applied, a folder receives the same timestamps whether it is processed alone or with the entire collection. The command refuses a sequence that would cross midnight.

## Setup

The project uses [uv](https://docs.astral.sh/uv/) and requires ExifTool for metadata reads and writes.

```bash
uv sync
exiftool -ver
```

On macOS, ExifTool can be installed with Homebrew if it is not already available:

```bash
brew install exiftool
```

## Review a plan

A normal invocation is always a dry run. `--root` is required so the command cannot accidentally choose a photograph directory.

```bash
uv run scan-metadata --root /Users/bwb/Pictures/Scans
```

Review the folder order, timestamps, descriptions, skipped-folder diagnostics, and same-date group summary before applying anything. To inspect one or more folders, repeat `--only`; same-date siblings still contribute to the selected folder's stable offset.

```bash
uv run scan-metadata \
  --root /Users/bwb/Pictures/Scans \
  --only 1997-03-06-In-the-woods
```

Use `--start HH:MM[:SS]` or `--interval-minutes N` to change the schedule. The interval must be positive and the resulting sequence must remain on the folder date.

## Apply and verify metadata

Use `--apply` only after reviewing the dry run. For the first production run, retain ExifTool's `_original` files with `--backup`:

```bash
uv run scan-metadata \
  --root /path/to/a/temporary/Scans-copy \
  --only 1997-03-06-In-the-woods \
  --apply \
  --backup
```

Test the command on a temporary copy before replacing `/path/to/a/temporary/Scans-copy` with the real root. Without `--backup`, ExifTool overwrites the original file container after updating metadata.

The tool writes these groups:

- Capture time: EXIF `DateTimeOriginal`, `CreateDate`, and `ModifyDate`, plus XMP `DateCreated`.
- Caption: EXIF `ImageDescription`, IPTC `Caption-Abstract`, and XMP `Description`.
- Title: IPTC `ObjectName`, XMP `Title`, and XMP Photoshop `Headline`.
- Keyword: IPTC `Keywords` and XMP `Subject`.

Descriptions must fit the 64-byte legacy IPTC title and keyword limit. UTF-8 descriptions are accepted and are never silently truncated.

After every apply operation, the command reads all required fields back and checks ExifTool's `ImageDataHash` before and after the write. A missing field, incorrect value, changed JPEG image payload, or ExifTool failure produces a nonzero exit with per-file diagnostics.

ExifTool can update earlier files before encountering a later failure. Keep the error output, restore affected files from their `_original` copies or your photograph backup if necessary, correct the cause, and rerun the same deterministic command.

Tag files before importing them into Photos. Updating a file after it has already been imported does not update the existing Photos library item automatically.

## Apple Photos captions and Shared Albums

After importing a tagged file into Photos on Mac, select it, open the Info panel with Command-I, and confirm the expected title or caption. Apple documents the library fields in [Add titles, captions, and more to photos and videos on Mac](https://support.apple.com/guide/photos/phta4e5a733f/mac).

Apple Photos Shared Albums do not turn embedded JPEG captions into visible comments. Adding a visible Shared Album comment therefore requires separate manual entry; the metadata command does not claim to automate that operation. Apple documents the distinct comment field in [Add, remove, and edit photos and videos in a shared album on Mac](https://support.apple.com/guide/photos/pht5f6df5f0/mac).

If participants must view and edit the Photos caption itself, evaluate iCloud Shared Photo Library instead of Shared Albums. Apple documents shared-library caption collaboration in [What is iCloud Shared Photo Library in Photos on Mac?](https://support.apple.com/guide/photos/pht153ab3a01/mac).

The Apple-specific acceptance record is in [`docs/photos-acceptance.md`](docs/photos-acceptance.md).

## Google Photos album sharing

`google-photos-upload` is the primary large-album sharing workflow. It reuses the metadata planner, creates a new album owned by the authenticated Google account and this OAuth client, adds a visible dated heading before each scan folder, and supplies the exact folder-derived text as every photograph's native Google Photos description.

The workflow is implemented as an ordinary tested repository command, not an agent skill. Upload correctness, OAuth storage, and recovery must work without Codex; a future skill could only provide optional setup guidance around these commands.

### Configure Google OAuth once

1. In Google Cloud, create or select a project, enable the Google Photos Library API, and configure its OAuth consent screen. Google documents this in [Configure your app](https://developers.google.com/photos/overview/configure-your-app).
2. Create an OAuth client ID for a Desktop app. If the consent screen is in testing, add the Google account that will own the album as a test user.
3. Download the client JSON to a private location outside this repository, such as `/Users/bwb/.config/photo-tools/google-photos-client.json`. Never copy it into the scan root, upload journal, or source tree.
4. Run `uv sync`. On the first explicit upload, the command opens Google's installed-application authorization flow. Refreshable authorization is stored in the operating-system credential store through `keyring`; access tokens remain in memory.

The command requests only `photoslibrary.appendonly` and `photoslibrary.readonly.appcreateddata`. Google Photos does not support service accounts for this workflow. Resources remain associated with the OAuth client ID that created them, so preserve that client configuration.

### Preview locally

Preview is the default and performs no OAuth flow or Google request:

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans"
```

The output contains the destination title, estimated Original-quality bytes, dated folder headings, ordered filenames, and exact native descriptions. Repeat `--only` to preview selected folders without changing their relative order. Add `--manifest /path/to/google-album.md` to save the same plan as a Markdown audit artifact.

### Upload explicitly

After reviewing the preview, upload with the external client configuration:

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans" \
  --client-config /Users/bwb/.config/photo-tools/google-photos-client.json \
  --upload
```

The default journal is `ROOT/.scan-tools/google-photos-ALBUM-TITLE.json`; use `--journal /another/path.json` to select a different location. It contains source paths and hashes, the album ID and URL, confirmed headings and media IDs, and any uncertain operation. It contains no OAuth tokens or client credentials.

Google's Library API accepts uploads in two stages and stores them at Original quality. These files consume the authenticated account's Google storage, and an album can contain at most 20,000 items. The API can add media only to albums created by this application, so the command intentionally has no option for an existing manually created album. See Google's [upload guidance](https://developers.google.com/photos/library/guides/upload-media) and [app-created content overview](https://developers.google.com/photos/library/guides/get-started-library).

### Resume or resolve an uncertain request

A rerun with the same root, title, filters, client configuration, and journal skips confirmed work. It refuses changed source files. Rate limits and failures confirmed before acceptance receive bounded retries; a timeout, interruption, or server failure after a mutating request may have reached Google and is recorded as uncertain without automatic retry.

Inspect Google Photos and the journal before resolving uncertainty. If the operation did not complete, resume it with:

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans" \
  --client-config /Users/bwb/.config/photo-tools/google-photos-client.json \
  --upload \
  --resolve-uncertain pending
```

If an uncertain album, heading, or media creation did complete, use `--resolve-uncertain completed` with the remote IDs requested by the error. Album creation also requires `--resolved-url`. Do not guess these values: resolving an accepted operation as pending can create a duplicate.

### Share once after upload

The current Google Photos API cannot enable album sharing. When upload is complete, the command prints the album URL. Open it in Google Photos, choose specific recipients or link sharing, and review whether collaborators may add photographs, comments, and likes. Anyone who receives a shared link can forward it; Google explains direct sharing, link sharing, and link reset controls in [Share photos and videos](https://support.google.com/photos/answer/6131416) and [Shared album privacy controls](https://support.google.com/photos/answer/9789702).

Google Photos is a presentation copy, not the metadata archive. Native Google descriptions may not be written back into downloaded JPEGs. Keep the tagged originals and their EXIF, IPTC, and XMP metadata.

### Manual Google Photos acceptance check

Use two disposable fixture folders with distinct descriptions and a temporary test album:

1. Run `scan-metadata --apply --backup` against the temporary scan root.
2. Run `google-photos-upload` without `--upload` and review both headings, filenames, descriptions, and the byte estimate.
3. Record source hashes, then rerun with the external client configuration and `--upload`.
4. Confirm both visible headings, deterministic group order, and native per-photo descriptions in Google Photos.
5. Share the completed album manually and verify headings and descriptions from a second account or private browser context.
6. Confirm source hashes are unchanged, then remove the temporary Google Photos album when the check is complete.

Record the platform, browser, API behavior, and observations in [`docs/google-photos-acceptance.md`](docs/google-photos-acceptance.md). This check is separate from the automated suite because it creates remote data, consumes storage until cleanup, and requires interactive Google authorization and sharing.

## Migration from the scan-folder helper

This repository command supersedes `Scans/.scan-tools/tag_scans.py`. The legacy script starts every folder at noon, so folders sharing a date receive overlapping timestamps. The new planner assigns one continuous range across all same-date folders.

The migration does not delete or modify `Scans/.scan-tools/tag_scans.py` or its generated `Scans/.scan-tools/exiftool.args`. Keep both until the new dry-run output and a backup-enabled production run have been reviewed. Cleanup requires a separate explicit decision.

## Development

Automated tests use generated fixtures and temporary copies, never the photograph collection:

```bash
uv run pytest
```
