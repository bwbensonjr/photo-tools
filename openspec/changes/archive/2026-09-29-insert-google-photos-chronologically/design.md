# Design

## Context

See `proposal.md` for motivation and the Google Photos album-sharing delta for required behavior.

The uploader has a complete, deterministic folder and photograph plan and a journal that maps every confirmed folder heading and photograph key to its Google Photos enrichment or media ID. Additive journal extension now preserves that state when entirely new folders appear. The current client nevertheless sends `LAST_IN_ALBUM` for every heading and media batch, so an older folder added later is placed at the end.

The Google Photos Library API supports `FIRST_IN_ALBUM`, `LAST_IN_ALBUM`, `AFTER_MEDIA_ITEM`, and `AFTER_ENRICHMENT_ITEM` positions. Album-scoped media search returns media items in album order and the existing read-only application-data scope is sufficient for application-created items. Album search does not return enrichment items, so existing heading placement cannot be independently reconstructed from Google; the journal remains authoritative for enrichment IDs.

## Goals / Non-Goals

**Goals:**

- Position new headings and media relative to confirmed application-created items so the complete scan-plan order is preserved.
- Validate the remotely observable application-created media sequence before relying on journal IDs as insertion anchors.
- Make positioned uploads resumable across heading creation, partial media results, batches larger than 50 items, timeouts, and explicit uncertainty resolution.
- Preserve the existing journal and authenticated album without re-uploading confirmed photographs.

**Non-Goals:**

- Reorder an album that has already drifted from the journal; drift requires user review rather than an automatic repair.
- Detect or reorder media created by other applications or added manually when it is not visible through the application-created-data scope.
- Reconstruct or validate the position or edited text of existing enrichments, because album media search omits enrichments.
- Change the deterministic local scan plan, embedded metadata, album ownership model, OAuth scopes, or sharing workflow.

## Decisions

### Derive every insertion position from the nearest confirmed predecessor

Walk the complete album plan from first to last while tracking the last confirmed media item. A pending heading uses `FIRST_IN_ALBUM` when it has no predecessor and otherwise uses `AFTER_MEDIA_ITEM` with the predecessor's media ID. The first pending photograph in that group uses `AFTER_ENRICHMENT_ITEM` with the confirmed heading ID. Subsequent photographs use `AFTER_MEDIA_ITEM` with the preceding photograph's confirmed media ID.

This inserts a new group before the next existing group without moving or recreating that group. It also handles consecutive new groups in the same gap: completion of the first new group supplies the predecessor for the next. Always appending and rebuilding the album were rejected because the former violates chronology and the latter duplicates remote work and disrupts the existing shared URL.

Represent positions as a validated value object or equivalent structured mapping accepted by both heading and media creation. The API adapter, rather than the orchestration loop, owns JSON field spelling and rejects an invalid combination of position type and relative ID.

### Upload contiguous pending runs instead of one flattened pending list

Partition each folder's planned photographs into contiguous unconfirmed runs. Split each run again at the API batch limit. The anchor for each request is the confirmed heading or immediately preceding confirmed photograph in plan order. After a successful batch, the last returned media ID becomes the anchor for the next batch.

This is necessary when a partially successful batch confirms later items but leaves a gap, or when an explicitly resolved uncertain operation produces confirmed items around an unconfirmed photo. Flattening all pending photos into one batch can move later photos ahead of already confirmed successors. Sequential runs preserve exact plan order with the API's after-item positioning primitive.

### Verify remote application-created media order before any incremental mutation

When an existing album has pending work, page through album-scoped media search before adding a heading or uploading bytes. Build the expected remote ID sequence by traversing the complete plan and selecting confirmed photographs. Require the returned IDs to match that sequence exactly. Missing, duplicate, reordered, or extra application-created media IDs are a remote-order drift error.

The check occurs before byte upload because upload tokens are remote mutations even though they do not yet create library items. A simple album `get` remains useful for identity and accessibility but cannot validate order. Trusting only journal IDs was rejected because a user can reorder or remove items in Google Photos after the journal records them.

The comparison is intentionally limited to application-created media visible under the existing scope. Existing enrichments and unrelated manually added media cannot be validated through this response; these API limits are reported in documentation rather than addressed with broader permissions.

### Persist the intended position for uncertain mutations

Extend uncertain heading and media records with the exact album-position mapping used for the request. Confirmed journal entries continue to store remote IDs, which are sufficient to recompute later anchors. When an uncertain operation is marked completed, the supplied IDs become confirmed and the next run derives its next position from those confirmations. When marked pending, the operation is retried at the same logical plan position after remote-order validation.

Position data is audit and recovery context, not a cached command to replay blindly. Recomputing from the current confirmed prefix prevents a stale relative ID from being reused after explicit resolution. Existing version-1 journals remain readable because the new uncertain fields are optional and the confirmed heading/media records already contain all required IDs; no journal version bump is required.

### Keep new-album behavior compatible while using the same position model

Initial album creation can continue placing the first heading at the end of the empty album, but all subsequent group construction should use explicit relative positions through the shared position model. Tests should assert complete request bodies rather than rely on Google defaults. This avoids maintaining separate ordering algorithms for initial and incremental uploads.

### Make chronological insertion visible in preview and progress

For an existing journal with additive folders, print the number of confirmed and pending items plus each pending group's planned predecessor or beginning-of-album placement before OAuth-backed mutation. Continue printing a folder only when it has pending work. If remote verification fails, identify the first order mismatch without printing credentials or remote content URLs.

The CLI remains explicit: the user reruns the complete-root command with the same album title and `--upload`. `--only` remains appropriate for creating a new filtered album, not extending an existing full-album journal.

## Risks / Trade-offs

- [Google changes or removes relative album positioning] -> Keep position construction isolated in the API adapter, fail confirmed preflight/request errors without falling back to append, and cover request bodies with fake-transport tests.
- [A user manually edits the album between verification and insertion] -> Perform verification immediately before mutation and retain conservative ambiguous-operation handling; the API offers no transaction spanning the read and writes.
- [Existing heading placement has drifted even though media order matches] -> Document that enrichments are not returned by album media search and require manual inspection when headings were edited or moved.
- [Manually added or non-application media is invisible to the current scope] -> State the validation boundary and avoid claiming automatic repair or a complete audit of foreign content.
- [Partial batch success leaves holes in a folder] -> Compute contiguous pending runs and position each run after its immediate confirmed predecessor.
- [A relative predecessor was deleted after preflight] -> Treat the request failure as confirmed or ambiguous according to the existing transport rules and stop without choosing a different anchor.
- [Remote validation adds latency for large albums] -> Use the maximum supported page size and perform the scan only when an existing album has pending work.

## Migration Plan

1. Add typed album-position construction and album-scoped, paginated media-order retrieval to the Google Photos client.
2. Add deterministic anchor calculation and contiguous pending-run planning independent of HTTP calls.
3. Preflight existing albums with pending work against the journaled confirmed-media sequence.
4. Change heading and media creation to use the planned positions and persist position context for uncertain operations.
5. Add fake-transport coverage for first, middle, last, consecutive-folder, multi-batch, partial-result, resume, and remote-drift cases.
6. Update CLI diagnostics and operational documentation, then perform a disposable application-owned album acceptance test before using the production album.

Rollback restores append-only request construction but must not automatically retry a partially completed chronological insertion. Preserve the journal and require inspection and uncertainty resolution before any older implementation resumes the album.
