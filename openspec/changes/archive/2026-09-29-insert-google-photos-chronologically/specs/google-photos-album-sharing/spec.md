# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
