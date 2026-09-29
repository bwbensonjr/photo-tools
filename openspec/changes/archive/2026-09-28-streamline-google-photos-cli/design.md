# Design

## Context

See `proposal.md` for motivation and the `google-photos-album-sharing` delta for observable behavior. The parser currently leaves `--client-config` unset, the command rejects uploads without it, the preview renderer owns the no-network advisory, the CLI owns the post-upload sharing advisory, and the upload loop has no mechanism for reporting the group it is processing.

Preview must remain free of OAuth and filesystem validation side effects. Upload state and remote mutation ordering must remain in the existing upload orchestrator, and credentials must continue to stay outside the repository and journal.

## Goals / Non-Goals

**Goals:**

- Make the documented private client configuration path convenient without weakening explicit upload or external-path checks.
- Emit one timely, deterministic status line for each folder that actually has pending remote work.
- Keep preview and completion output concise while preserving the detailed plan, final progress totals, and album URL.
- Keep progress behavior injectable and testable without Google access.

**Non-Goals:**

- Search multiple credential locations, create or download an OAuth client file, or change operating-system token storage.
- Add per-file progress, byte percentages, concurrency, terminal animation, or machine-readable output.
- Change sharing behavior, OAuth scopes, journal format, retry rules, or upload ordering.

## Decisions

### Resolve one default client path only for explicit uploads

Keep `--client-config` as an optional `Path` override. When `--upload` is present and the option is absent, resolve the selected path to `Path.home() / ".config" / "photo-tools" / "google-photos-client.json"`. Pass the selected path through the existing authorizer so repository-boundary validation, JSON validation, and credential handling remain centralized.

Resolve and validate this path after the local album plan is built and only on the upload branch. Preview therefore continues without reading home-directory configuration. Add a clear Google Photos configuration error for a missing, unreadable, or invalid selected file. Environment-variable search and platform-specific configuration directories were considered but rejected because they make path selection less predictable and are unnecessary for the documented macOS workflow.

### Report progress through an optional upload callback

Extend the upload orchestrator with an optional folder-progress callback rather than printing from the Google Photos domain module. For each group, first determine whether its heading or any media item is unconfirmed. Invoke the callback once with the exact `folder_name` immediately before the first pending remote mutation. Fully confirmed groups do not invoke it during resume.

The CLI supplies a callback that prints `uploading folder: <folder-name>`. Tests and non-CLI callers may omit or capture the callback. Printing directly inside the upload loop was rejected because it would couple reusable upload logic to terminal output and make tests less precise.

### Remove only the two requested advisory lines

Remove the no-OAuth sentence from `render_album_preview` and remove the manual-sharing sentence from successful CLI completion. Preserve the preview-only count, manifest notice, final confirmed/failed/uncertain totals, and `album ready: <URL>` line. Keep the manual sharing checklist in `README.md`, because the API limitation and user action remain true even though they need not be repeated after every upload.

## Risks / Trade-offs

- [A default path can hide which OAuth project is in use] -> Document the exact path and retain `--client-config` as an explicit override.
- [A progress line may be printed before an operation that immediately fails] -> Define the line as processing-start status, not confirmation; retain the journal-derived final or error summary as authoritative.
- [Resume behavior could announce already completed folders] -> Compute pending heading/media state before invoking the callback and test a partially and fully confirmed resume.
- [Removing advisory lines can affect consumers parsing human output] -> Preserve structured operational facts and document that no machine-readable output contract exists; update exact-output tests.

## Migration Plan

1. Add default-path resolution and update parser help and README examples.
2. Add the optional progress callback and CLI status formatter without changing remote operation order.
3. Remove the two advisory lines and update focused tests and documentation.
4. Run the full automated suite and strict OpenSpec validation.

Rollback restores the explicit `--client-config` requirement and the two advisory lines; the journal and remote albums require no migration.
