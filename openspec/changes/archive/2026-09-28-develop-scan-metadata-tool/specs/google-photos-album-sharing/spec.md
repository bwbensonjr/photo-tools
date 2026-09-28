# Spec Delta

## Purpose

Publish large scan collections to Google Photos with deterministic ordering, prominent descriptions, visible folder groupings, and recoverable user-authorized uploads.

## ADDED Requirements

### Requirement: Create an application-owned destination album
The workflow SHALL create a new Google Photos album owned by the authenticated user and managed by this application, and SHALL refuse to claim that it can populate or manage a manually created album through the restricted Google Photos API.

#### Scenario: User supplies a new album title
- **WHEN** the user explicitly starts an upload with a valid title
- **THEN** the workflow creates one application-owned album and records its stable identifier and Google Photos URL

#### Scenario: User requests an existing manual album
- **WHEN** the user supplies an album that was not created by this application
- **THEN** the workflow refuses the unsupported target and explains that Google limits API management to application-created content

### Requirement: Preserve deterministic album order and folder grouping
The workflow SHALL process selected folders in plan order, process each folder's JPEGs in scan order, and add a visible text heading before each folder group containing its date and derived description.

#### Scenario: Multiple folders share a date
- **WHEN** multiple selected folders share a date
- **THEN** their headings and photographs appear as contiguous groups in deterministic folder order without interleaving

#### Scenario: Upload is filtered
- **WHEN** the user selects only some folders from a complete plan
- **THEN** only those folders are represented, in the same relative order and with the same timestamps and descriptions as in the unfiltered plan

### Requirement: Populate the native Google Photos description
Every uploaded photograph SHALL receive the exact folder-derived text as its Google Photos media-item description in addition to retaining its embedded EXIF, IPTC, and XMP metadata.

#### Scenario: Uploaded photo is opened
- **WHEN** an uploaded photograph is viewed in Google Photos
- **THEN** its folder-derived text is available through Google Photos' native description field rather than only under embedded metadata shown as Other

### Requirement: Require explicit and reviewable upload
The workflow SHALL default to a non-networking preview and SHALL require an explicit upload option before authorizing or contacting Google Photos. The preview SHALL show the destination title, folder headings, ordered filenames, and per-photo descriptions.

#### Scenario: Upload is previewed
- **WHEN** the user supplies an album title without the explicit upload option
- **THEN** the workflow prints the complete ordered album plan without opening an OAuth flow, creating an album, or uploading files

### Requirement: Protect authorization material
The workflow SHALL keep OAuth client configuration and refresh tokens outside the repository and upload journal, request only the scopes required for application-created Google Photos content, and redact credentials from diagnostics.

#### Scenario: Authorization completes
- **WHEN** the user authorizes Google Photos access
- **THEN** no client credential or access or refresh token is written to the repository, scan metadata, upload manifest, or command output

### Requirement: Resume without duplicating confirmed uploads
The workflow SHALL maintain a non-secret upload journal that identifies the destination album, planned source files, content fingerprints, folder headings, completed remote items, and the first uncertain operation. It SHALL resume only confirmed incomplete work and SHALL require user resolution of ambiguous outcomes.

#### Scenario: Upload stops after a confirmed failure
- **WHEN** one folder uploads successfully and a later upload fails before Google accepts it
- **THEN** a resumed run skips the confirmed completed work and continues from the first confirmed incomplete item

#### Scenario: Upload outcome is ambiguous
- **WHEN** a timeout or interruption occurs after bytes or a create request may have reached Google
- **THEN** the workflow stops, records the uncertain item, and refuses to retry it automatically until the user resolves the journal state

### Requirement: Preserve local source photographs
Google Photos upload and album construction SHALL read the selected JPEGs without modifying or deleting them, and automated tests SHALL use generated fixtures and fake transports rather than the user's collection or Google services.

#### Scenario: Album upload succeeds
- **WHEN** an explicit upload completes
- **THEN** the local source photographs remain byte-for-byte unchanged

### Requirement: Hand off sharing to the user
After a successful upload, the workflow SHALL provide the Google Photos album URL and SHALL document that the user must configure people, link sharing, collaboration, comments, and likes in Google Photos.

#### Scenario: Album is ready to share
- **WHEN** every planned heading and photograph is confirmed in the destination album
- **THEN** the workflow reports completion, opens no sharing permission automatically, and gives the user the album URL and sharing checklist
