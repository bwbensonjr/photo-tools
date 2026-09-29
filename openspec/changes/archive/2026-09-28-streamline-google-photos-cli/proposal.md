# Proposal

## Why

The Google Photos upload command requires a repetitive OAuth configuration argument and emits advisory text that is no longer useful during routine use. Uploads also provide no folder-level status while potentially large groups are transferred, making a healthy long-running operation look idle.

## What Changes

- Default the OAuth client configuration to `~/.config/photo-tools/google-photos-client.json` for explicit uploads while retaining `--client-config` as an override.
- Fail with a clear configuration error when the selected OAuth client file does not exist or is invalid.
- Print the source folder name as each folder with pending remote work begins processing, including resumed uploads.
- Remove the preview sentence `no OAuth flow or Google Photos request was performed` while preserving local-only preview behavior.
- Remove the successful-upload sentence beginning `sharing remains manual` while continuing to print the album URL and document manual sharing in `README.md`.
- Update CLI, upload, and documentation tests to cover the concise output and default/override configuration behavior without contacting Google.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `google-photos-album-sharing`: Define the default external OAuth client path, folder-level progress output, concise preview output, and album-URL-only completion output while retaining documented manual sharing.

## Impact

- Affects `src/photo_tools/google_photos_cli.py`, the upload orchestration interface in `src/photo_tools/google_photos.py`, Google Photos CLI and upload tests, and Google Photos usage documentation in `README.md`.
- Does not change Google OAuth scopes, credential storage, album ordering, journal recovery, upload safety, or the requirement for explicit `--upload` before network access.
- Removes two human-facing informational lines; the CLI does not expose a machine-readable output compatibility guarantee.
