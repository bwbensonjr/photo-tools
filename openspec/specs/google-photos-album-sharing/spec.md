# google-photos-album-sharing Specification

## Purpose

Publish large scan collections to Google Photos with deterministic ordering, prominent descriptions, visible folder groupings, and recoverable user-authorized uploads.

## Requirements

### Requirement: Create an application-owned destination album
The workflow SHALL create a new Google Photos album owned by the authenticated user and managed by this application, and SHALL refuse to claim that it can populate or manage a manually created album through the restricted Google Photos API.

#### Scenario: User supplies a new album title
- **WHEN** the user explicitly starts an upload with a valid title
- **THEN** the workflow creates one application-owned album and records its stable identifier and Google Photos URL

#### Scenario: User requests an existing manual album
- **WHEN** the user supplies an album that was not created by this application
- **THEN** the workflow refuses the unsupported target and explains that Google limits API management to application-created content

### Requirement: Preserve deterministic album order and folder grouping
The workflow SHALL keep all folder groups in complete scan-plan order in a newly created or incrementally extended album, process each folder's JPEGs in scan order, and place a visible text heading immediately before each folder group containing its date and derived description.

#### Scenario: Multiple folders share a date
- **WHEN** multiple selected folders share a date
- **THEN** their headings and photographs appear as contiguous groups in deterministic folder order without interleaving

#### Scenario: Upload is filtered
- **WHEN** the user selects only some folders from a complete plan for a new album
- **THEN** only those folders are represented, in the same relative order and with the same timestamps and descriptions as in the unfiltered plan

#### Scenario: New folder belongs between existing groups
- **WHEN** an unchanged completed album is extended with a new folder whose complete-plan position falls between two confirmed folder groups
- **THEN** the new heading and photographs are inserted after the preceding group and before the following group without re-uploading either existing group

#### Scenario: New folder precedes every existing group
- **WHEN** an unchanged completed album is extended with a new folder whose complete-plan position is first
- **THEN** the new heading and photographs become the first contiguous group in the album

#### Scenario: Multiple new folders share an insertion gap
- **WHEN** two or more new folders belong between the same previously confirmed groups
- **THEN** all new headings and photographs appear contiguously in complete-plan order within that gap

### Requirement: Report folder-level upload progress
The workflow SHALL print the exact source folder name before processing each folder that has pending remote work. A resumed upload SHALL omit folder progress for groups whose heading and photographs are already confirmed.

#### Scenario: Folder begins uploading
- **WHEN** a selected folder has an unconfirmed heading or photograph
- **THEN** the command prints that folder's source name before issuing its next remote mutation

#### Scenario: Confirmed folder is skipped on resume
- **WHEN** a resumed upload reaches a folder whose heading and photographs are all confirmed in the journal
- **THEN** the command neither repeats remote work nor prints an uploading status for that folder

### Requirement: Populate the native Google Photos description
Every uploaded photograph SHALL receive the exact folder-derived text as its Google Photos media-item description in addition to retaining its embedded EXIF, IPTC, and XMP metadata.

#### Scenario: Uploaded photo is opened
- **WHEN** an uploaded photograph is viewed in Google Photos
- **THEN** its folder-derived text is available through Google Photos' native description field rather than only under embedded metadata shown as Other

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

### Requirement: Resume without duplicating confirmed uploads
The workflow SHALL maintain a non-secret upload journal that identifies the destination album, planned source files, content fingerprints, folder headings, completed remote items, insertion anchors, and the first uncertain operation. It SHALL resume only confirmed incomplete work, preserve chronological position across resumed batches, and SHALL require user resolution of ambiguous outcomes.

#### Scenario: Upload stops after a confirmed failure
- **WHEN** one folder uploads successfully and a later upload fails before Google accepts it
- **THEN** a resumed run skips the confirmed completed work and continues from the first confirmed incomplete item

#### Scenario: Upload outcome is ambiguous
- **WHEN** a timeout or interruption occurs after bytes or a positioned create request may have reached Google
- **THEN** the workflow stops, records the uncertain item and its intended position, and refuses to retry it automatically until the user resolves the journal state

#### Scenario: New scan folder is added after album completion
- **WHEN** the complete source plan contains one or more new folder groups while every previously journaled folder and photograph remains unchanged and in the same relative order
- **THEN** the workflow extends the journal, preserves all confirmed remote items, and uploads only the new folder groups at their complete-plan positions

#### Scenario: Existing journaled content changes
- **WHEN** a previously journaled folder, photograph, description, order, size, or content fingerprint changes or disappears
- **THEN** the workflow refuses to extend the journal before contacting Google Photos

#### Scenario: Positioned folder upload stops between batches
- **WHEN** a folder larger than one remote batch is partially confirmed before a confirmed failure
- **THEN** a resumed run positions the remaining photographs after the last confirmed photograph in that folder and before the following folder group

### Requirement: Validate remote order before incremental insertion
Before inserting new groups into an existing album, the workflow SHALL compare the remotely visible order of previously confirmed media items with their journaled complete-plan order and SHALL perform no album mutation when confirmed media are missing, duplicated, unexpected, or reordered.

#### Scenario: Remote order matches the journal
- **WHEN** every confirmed media item appears exactly once in the existing album and in journaled order
- **THEN** the workflow may use the confirmed remote IDs as chronological insertion anchors

#### Scenario: User manually reordered the album
- **WHEN** the remotely visible order of confirmed media items differs from the journaled order
- **THEN** the workflow exits with a remote-order drift error before adding a heading or uploading photograph bytes

#### Scenario: Confirmed item is absent remotely
- **WHEN** a media item recorded as confirmed in the journal is not present in the destination album
- **THEN** the workflow exits with a remote-order drift error before any album mutation

### Requirement: Preserve local source photographs
Google Photos upload and album construction SHALL read the selected JPEGs without modifying or deleting them, and automated tests SHALL use generated fixtures and fake transports rather than the user's collection or Google services.

#### Scenario: Album upload succeeds
- **WHEN** an explicit upload completes
- **THEN** the local source photographs remain byte-for-byte unchanged

### Requirement: Hand off sharing to the user
After a successful upload, the workflow SHALL print the Google Photos album URL without printing a sharing checklist or a `sharing remains manual` advisory. The documentation SHALL continue to explain that the user must configure people, link sharing, collaboration, comments, and likes in Google Photos.

#### Scenario: Album is ready to share
- **WHEN** every planned heading and photograph is confirmed in the destination album
- **THEN** the workflow reports completion and the album URL, does not open sharing permission automatically, and does not print the removed manual-sharing advisory
