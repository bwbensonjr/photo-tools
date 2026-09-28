# Google Photos Manual Acceptance Record

Follow the manual Google Photos acceptance procedure in `README.md` with two disposable tagged fixture folders and a temporary application-created album. Do not upload the production scan root for this test.

## Environment

- Date: 2026-09-28
- Operating system: macOS 26.6.2 (build 25G83)
- Browser and version: Google Chrome 154.0.8037.58
- `photo-tools` revision: `f20d62f9da208936372b06882285bfa87b6b350f` with the current uncommitted implementation
- Google Photos Library API behavior observed: Installed-application OAuth succeeded after the account was added as an OAuth test user. The API created an application-owned album, two dated text enrichments, and two media items with native descriptions. Sharing remained a manual Google Photos action as designed.

## Results

- Local preview completed without OAuth or network access: Yes
- First dated folder heading visible: Yes, `2001-01-01 - Acceptance First`
- First photograph native description visible: Yes, `Acceptance First`
- Second dated folder heading visible: Yes, `2001-01-02 - Acceptance Second`
- Second photograph native description visible: Yes, `Acceptance Second`
- Folder groups remain contiguous and ordered: Yes
- Album shared manually: Yes
- Second account or private-context view confirmed: Yes
- Source SHA-256 hashes unchanged: Yes
  - `first.jpg`: `7800e95a79e9e36760aa653f3aa2bf21e082b757570247d5c2484b708d7b51df`
  - `second.jpg`: `f8a0f7eb882ac3470d96e6409703611d03bb0105935d3a8a815d58500f5b112c`
- Temporary album removed after testing: No; retained for user review and manual cleanup

## Notes

The first authorization attempts were blocked while the OAuth application was in testing mode because the account had not yet been listed as a test user. Authorization and upload completed after `bwbensonjr@gmail.com` was added as a test user. The completed journal recorded two confirmed headings, two confirmed media items, no failed operations, and no uncertain operation. The temporary album is `Photo Tools Acceptance 2026-09-28`.

Do not record client secrets, authorization codes, access tokens, refresh tokens, or authorization headers. None are recorded here.
