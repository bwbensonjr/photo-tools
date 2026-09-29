# Photo Tools

Command-line tools for tagging scanned JPEGs and uploading ordered albums to Google Photos.

## Setup

Install [uv](https://docs.astral.sh/uv/) and ExifTool, then install the project dependencies:

```bash
brew install exiftool
uv sync
```

Scans must be JPEG files directly inside folders named `YYYY-MM-DD-description`:

```text
Scans/
  1997-03-06-Birthdays/
  1997-03-06-In-the-woods/
```

Folders sharing a date are ordered by folder name. Files are ordered by filename. Timestamps begin at noon by default and advance one minute continuously across all folders on the date, preventing interleaving.

## Tag photo metadata

Preview the complete plan without changing files:

```bash
uv run scan-metadata --root /Users/bwb/Pictures/Scans
```

Limit the output or update to selected folders by repeating `--only`:

```bash
uv run scan-metadata \
  --root /Users/bwb/Pictures/Scans \
  --only 1997-03-06-In-the-woods
```

Change the daily starting time or interval with `--start HH:MM[:SS]` and `--interval-minutes N`.

After reviewing the dry run, apply the metadata. Use `--backup` on the first production run to keep ExifTool `_original` files:

```bash
uv run scan-metadata \
  --root /Users/bwb/Pictures/Scans \
  --apply \
  --backup
```

The command writes capture dates, descriptions, titles, and keywords to EXIF, IPTC, and XMP fields, then verifies the values and `ImageDataHash`. A verification failure exits nonzero. Tag photographs before importing them into a photo library.

## Upload to Google Photos

### Configure OAuth once

1. Create a Google Cloud project and enable the Google Photos Library API.
2. Configure the OAuth consent screen. If the application is in testing mode, add the album owner as a test user.
3. Create a Desktop app OAuth client.
4. Save its JSON file at `~/.config/photo-tools/google-photos-client.json`.

Keep this file outside the repository and scan folders. Refresh credentials are stored in the operating-system credential store.

### Preview an album

Preview is local-only and does not contact Google:

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans"
```

The preview shows folder headings, filenames, descriptions, and estimated upload size. Use repeated `--only` options to select folders or `--manifest /path/to/album.md` to save the plan.

### Upload an album

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans" \
  --upload
```

Use `--client-config /path/to/client.json` to override the default OAuth file. The command creates a new app-owned album, prints each folder as it uploads, and prints the album URL when complete.

Uploads use Original quality and consume Google storage. Albums are limited to 20,000 items. The API can manage only albums and media created by this application.

Progress is stored in `ROOT/.scan-tools/google-photos-ALBUM-TITLE.json`. Use `--journal /path/to/journal.json` to override it. Rerunning the same command resumes confirmed incomplete work and refuses files whose contents changed.

### Resolve an uncertain upload

If the command reports that an operation may have completed, inspect the album and journal before continuing.

If the operation did not complete:

```bash
uv run google-photos-upload \
  --root /Users/bwb/Pictures/Scans \
  --album-title "Family scans" \
  --upload \
  --resolve-uncertain pending
```

If it did complete, use `--resolve-uncertain completed` with the remote IDs requested by the error. Completed album creation also requires `--resolved-url`. Do not guess these values; marking a completed operation pending can create duplicates.

Google does not allow this API to enable sharing. Open the printed album URL and configure recipients, link sharing, collaboration, comments, and likes manually.

## Tests

```bash
uv run pytest
```

Tests use generated fixtures and temporary files, not the photograph collection or Google services.
