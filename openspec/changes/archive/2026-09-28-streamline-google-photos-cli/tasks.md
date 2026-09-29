# Tasks

## 1. Default OAuth Client Configuration

- [x] 1.1 Add upload-only resolution of `~/.config/photo-tools/google-photos-client.json` while retaining `--client-config` as an override; verify CLI tests cover default selection, override selection, and that preview does not inspect or require either path.
- [x] 1.2 Add clear missing, unreadable, and invalid client-configuration errors without exposing configuration contents; verify fake-authorizer and CLI tests fail before any Google Photos request and retain repository-boundary and redaction checks.
- [x] 1.3 Update `README.md` upload and recovery examples to use the default path, document the override, and verify documentation tests cover the exact default location and optional flag.

## 2. Concise Progress and Completion Output

- [x] 2.1 Remove the no-OAuth advisory from the local preview while preserving the complete plan and preview-only summary; verify preview and manifest tests assert local-only behavior through side effects and confirm the removed sentence is absent.
- [x] 2.2 Add an optional folder-progress callback to upload orchestration and have the CLI print `uploading folder: <folder-name>` before each group with pending remote work; verify request-order tests cover multiple folders, a partially completed resume, and omission of fully confirmed groups.
- [x] 2.3 Remove the successful-upload `sharing remains manual` advisory while preserving final progress totals and `album ready: <URL>`; verify CLI tests assert the concise output and `README.md` still documents the manual sharing checklist.

## 3. Integration Verification

- [x] 3.1 Run `uv run pytest -q` and `openspec validate streamline-google-photos-cli --strict`; verify all automated tests and the change artifacts pass without contacting Google or modifying the photograph collection.
