# Spec Delta

## ADDED Requirements

### Requirement: Report folder-level upload progress
The workflow SHALL print the exact source folder name before processing each folder that has pending remote work. A resumed upload SHALL omit folder progress for groups whose heading and photographs are already confirmed.

#### Scenario: Folder begins uploading
- **WHEN** a selected folder has an unconfirmed heading or photograph
- **THEN** the command prints that folder's source name before issuing its next remote mutation

#### Scenario: Confirmed folder is skipped on resume
- **WHEN** a resumed upload reaches a folder whose heading and photographs are all confirmed in the journal
- **THEN** the command neither repeats remote work nor prints an uploading status for that folder

## MODIFIED Requirements

### Requirement: Require explicit and reviewable upload
The workflow SHALL default to a non-networking preview and SHALL require an explicit upload option before authorizing or contacting Google Photos. The preview SHALL show the destination title, folder headings, ordered filenames, and per-photo descriptions without appending an advisory sentence that no OAuth flow or Google Photos request occurred.

#### Scenario: Upload is previewed
- **WHEN** the user supplies an album title without the explicit upload option
- **THEN** the workflow prints the complete ordered album plan without opening an OAuth flow, creating an album, uploading files, or printing the removed no-OAuth advisory sentence

### Requirement: Protect authorization material
For an explicit upload, the workflow SHALL use `~/.config/photo-tools/google-photos-client.json` as the default OAuth client configuration and SHALL allow `--client-config` to override that path. It SHALL keep OAuth client configuration and refresh tokens outside the repository and upload journal, fail clearly when the selected configuration is missing or invalid, request only the scopes required for application-created Google Photos content, and redact credentials from diagnostics.

#### Scenario: Default client configuration is used
- **WHEN** the user explicitly uploads without `--client-config`
- **THEN** the workflow expands and uses `~/.config/photo-tools/google-photos-client.json`

#### Scenario: Client configuration is overridden
- **WHEN** the user explicitly uploads with `--client-config`
- **THEN** the workflow uses the supplied external path instead of the default path

#### Scenario: Selected client configuration is unavailable
- **WHEN** the selected default or override path is missing, unreadable, or invalid
- **THEN** the workflow exits before contacting Google Photos and identifies the configuration problem without exposing secret values

#### Scenario: Authorization completes
- **WHEN** the user authorizes Google Photos access
- **THEN** no client credential or access or refresh token is written to the repository, scan metadata, upload manifest, or command output

### Requirement: Hand off sharing to the user
After a successful upload, the workflow SHALL print the Google Photos album URL without printing a sharing checklist or a `sharing remains manual` advisory. The documentation SHALL continue to explain that the user must configure people, link sharing, collaboration, comments, and likes in Google Photos.

#### Scenario: Album is ready to share
- **WHEN** every planned heading and photograph is confirmed in the destination album
- **THEN** the workflow reports completion and the album URL, does not open sharing permission automatically, and does not print the removed manual-sharing advisory
