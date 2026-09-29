# Proposal

## Why

Incremental uploads currently append newly discovered scan folders to the end of an existing Google Photos album, even when the folders belong earlier in the deterministic scan plan. This breaks the chronological album ordering that the workflow is intended to preserve.

## What Changes

- Insert each newly added folder heading and its photographs at the folder's chronological position in the existing application-owned album.
- Preserve the ordering of photographs within a folder and of multiple newly inserted folders that occupy the same gap.
- Verify that the remotely visible media-item order still agrees with the journal before using recorded remote items as insertion anchors, and stop without mutation when manual reordering or other drift makes the anchor unsafe.
- Resume interrupted chronological insertions without duplicating confirmed headings or photographs or reversing partially completed batches.
- Keep unchanged journaled folders and photographs untouched during an incremental upload.
- Document chronological incremental upload behavior, remote-order drift handling, and the existing uncertainty-resolution workflow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `google-photos-album-sharing`: Extend deterministic album ordering and resumable upload requirements so newly added folder groups are inserted at their planned chronological positions in an existing application-owned album.

## Impact

- Affects Google Photos album-position request construction, incremental upload orchestration, journal validation and recovery, CLI diagnostics, documentation, and fake-transport tests.
- Uses the existing Google Photos Library API and OAuth scopes; no new dependency or credential scope is expected.
- Adds read-only remote album-order verification before an incremental mutation and uses stored application-created media and enrichment IDs as relative insertion anchors.
