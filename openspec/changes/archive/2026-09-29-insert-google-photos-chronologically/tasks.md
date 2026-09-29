# Tasks

## 1. Google Photos positioning and order reads

- [x] 1.1 Add validated album-position construction for beginning-of-album, after-media, and after-enrichment placement, update heading and media request builders to accept it, and verify focused client tests assert the exact JSON bodies and reject invalid position/relative-ID combinations.
- [x] 1.2 Add paginated album-scoped media search that returns application-created media IDs in remote album order, and verify fake-transport tests cover multiple pages, malformed responses, and confirmed request failures.

## 2. Deterministic insertion and journal recovery planning

- [x] 2.1 Add a pure insertion planner that derives heading anchors and contiguous pending photo runs from complete plan order plus confirmed journal IDs, and verify unit tests cover first, middle, last, consecutive-folder, partial-prefix, interior-gap, and over-50-photo cases.
- [x] 2.2 Record intended album positions with uncertain heading and media operations while keeping existing version-1 journals readable, and verify journal tests cover completed and pending resolution followed by recomputed anchors.

## 3. Safe chronological upload orchestration

- [x] 3.1 Compare the paginated remote media-ID sequence with the journaled confirmed sequence before any existing-album mutation, and verify tests show matching order proceeds while missing, duplicate, extra, and reordered IDs stop before heading creation or byte upload.
- [x] 3.2 Execute headings and contiguous photo batches at their planned positions, updating the anchor after every confirmed batch, and verify fake-transport tests demonstrate chronological insertion at the beginning and middle plus multiple new folders in one gap without requests for confirmed photos.
- [x] 3.3 Preserve chronological position across confirmed failures, partial batch results, keyboard interruption, ambiguous requests, and explicit uncertainty resolution, and verify resume tests prove no confirmed item is duplicated or reversed.

## 4. Operator feedback and documentation

- [x] 4.1 Report pending groups and their planned beginning-of-album or predecessor placement before mutation, keep credential and URL redaction intact, and verify CLI tests cover incremental status and remote-order drift output.
- [x] 4.2 Update `README.md` with the same-title complete-root command, chronological insertion guarantees, validation boundaries for enrichments and non-application media, and recovery guidance; verify documentation tests cover the new operational language.
- [x] 4.3 Extend the Google Photos manual acceptance procedure for a disposable album with existing early and late groups plus a newly inserted middle group, and verify the record requires visual confirmation of heading and photo order before production use.

## 5. Integration verification

- [x] 5.1 Run `uv run pytest`, `openspec validate insert-google-photos-chronologically --strict`, and a local-only production-root preview; verify all commands succeed without modifying photographs, the production journal, or Google Photos.
