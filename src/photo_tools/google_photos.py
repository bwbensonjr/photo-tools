"""Plan and perform recoverable uploads to app-created Google Photos albums."""

from __future__ import annotations

import hashlib
import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

import requests

from photo_tools.scan_metadata import Plan, PlannedPhoto, ScanMetadataError


API_BASE = "https://photoslibrary.googleapis.com/v1"
UPLOAD_URL = f"{API_BASE}/uploads"
APPEND_SCOPE = "https://www.googleapis.com/auth/photoslibrary.appendonly"
READ_SCOPE = "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata"
OAUTH_SCOPES = (APPEND_SCOPE, READ_SCOPE)
MAX_ALBUM_ITEMS = 20_000
MAX_BATCH_ITEMS = 50
MAX_DESCRIPTION_LENGTH = 1_000
JOURNAL_VERSION = 1


class GooglePhotosError(ScanMetadataError):
    """A user-facing Google Photos workflow error."""


class ConfirmedRequestError(GooglePhotosError):
    """A request is known not to have completed successfully."""


class AmbiguousRequestError(GooglePhotosError):
    """A mutating request may have completed remotely."""


class TransportFailure(Exception):
    """A transport failure with an explicit acceptance classification."""

    def __init__(self, message: str, *, may_have_been_accepted: bool) -> None:
        super().__init__(message)
        self.may_have_been_accepted = may_have_been_accepted


@dataclass(frozen=True)
class AlbumPhoto:
    """One source photograph and its Google Photos presentation metadata."""

    key: str
    source: Path
    filename: str
    description: str


@dataclass(frozen=True)
class AlbumGroup:
    """One visible folder group in a Google Photos album."""

    key: str
    folder_name: str
    heading: str
    photos: tuple[AlbumPhoto, ...]


@dataclass(frozen=True)
class AlbumPlan:
    """A deterministic local representation of a proposed Google album."""

    root: Path
    title: str
    groups: tuple[AlbumGroup, ...]
    duplicate_date_counts: tuple[tuple[dt.date, int], ...]

    @property
    def photo_count(self) -> int:
        return sum(len(group.photos) for group in self.groups)

    @property
    def total_bytes(self) -> int:
        return sum(photo.source.stat().st_size for group in self.groups for photo in group.photos)


@dataclass(frozen=True)
class HttpResponse:
    """Transport-neutral HTTP response used by the API adapter."""

    status_code: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> dict[str, Any]:
        try:
            value = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfirmedRequestError("Google Photos returned invalid JSON") from error
        if not isinstance(value, dict):
            raise ConfirmedRequestError("Google Photos returned an unexpected JSON value")
        return value

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpTransport(Protocol):
    """Minimal injectable transport used by the Google Photos client."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        timeout: float = 60.0,
    ) -> HttpResponse: ...


class CredentialStore(Protocol):
    """Storage abstraction for OAuth authorized-user JSON."""

    def get(self, account: str) -> str | None: ...

    def set(self, account: str, value: str) -> None: ...


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def repository_root() -> Path:
    """Return the checkout root containing the installed source module."""
    return Path(__file__).resolve().parents[2]


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove common OAuth values and explicitly known secrets from diagnostics."""
    redacted = text
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    patterns = (
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+",
        r'(?i)("?(?:access_token|refresh_token|client_secret)"?\s*[:=]\s*")[^"]+',
        r"(?i)((?:access_token|refresh_token|client_secret)\s*[:=]\s*)[^\s,;]+",
    )
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    return redacted


def build_album_plan(
    scan_plan: Plan,
    entries: Sequence[PlannedPhoto],
    *,
    title: str,
) -> AlbumPlan:
    """Convert selected metadata entries into contiguous Google album groups."""
    clean_title = title.strip()
    if not clean_title:
        raise GooglePhotosError("album title must not be empty")

    groups: list[AlbumGroup] = []
    current_folder: Path | None = None
    current_entries: list[PlannedPhoto] = []

    def append_group(folder_entries: Sequence[PlannedPhoto]) -> None:
        if not folder_entries:
            return
        first = folder_entries[0]
        heading = f"{first.date.isoformat()} - {first.description}"
        if len(heading) > MAX_DESCRIPTION_LENGTH:
            raise GooglePhotosError(
                f"album heading exceeds {MAX_DESCRIPTION_LENGTH} characters: {heading!r}"
            )
        photos: list[AlbumPhoto] = []
        for entry in folder_entries:
            if len(entry.description) > MAX_DESCRIPTION_LENGTH:
                raise GooglePhotosError(
                    "Google Photos description exceeds "
                    f"{MAX_DESCRIPTION_LENGTH} characters: {entry.description!r}"
                )
            relative = entry.photo.relative_to(scan_plan.root).as_posix()
            photos.append(
                AlbumPhoto(
                    key=relative,
                    source=entry.photo,
                    filename=entry.photo.name,
                    description=entry.description,
                )
            )
        groups.append(
            AlbumGroup(
                key=first.folder.relative_to(scan_plan.root).as_posix(),
                folder_name=first.folder.name,
                heading=heading,
                photos=tuple(photos),
            )
        )

    for entry in entries:
        if entry.folder != current_folder:
            append_group(current_entries)
            current_folder = entry.folder
            current_entries = []
        current_entries.append(entry)
    append_group(current_entries)

    album_plan = AlbumPlan(
        root=scan_plan.root,
        title=clean_title,
        groups=tuple(groups),
        duplicate_date_counts=scan_plan.duplicate_date_counts,
    )
    if album_plan.photo_count > MAX_ALBUM_ITEMS:
        raise GooglePhotosError(
            f"album has {album_plan.photo_count} photographs; Google Photos limits "
            f"albums to {MAX_ALBUM_ITEMS} items"
        )
    return album_plan


def render_album_preview(plan: AlbumPlan) -> str:
    """Render the complete local-only Google Photos album preview."""
    lines = [
        f'Google Photos album preview: "{plan.title}"',
        f"source: {plan.root}",
        f"estimated original-quality upload: {plan.total_bytes} bytes",
    ]
    if plan.duplicate_date_counts:
        lines.append(
            "same-date groups: "
            + ", ".join(
                f"{date.isoformat()} ({count} folders)"
                for date, count in plan.duplicate_date_counts
            )
        )
    for group in plan.groups:
        lines.extend(["", f"heading: {group.heading}"])
        for photo in group.photos:
            lines.append(f'  {photo.filename} -> description "{photo.description}"')
    lines.extend(
        [
            "",
            f"preview only: {plan.photo_count} photos in {len(plan.groups)} folder groups",
            "no OAuth flow or Google Photos request was performed",
        ]
    )
    return "\n".join(lines)


def album_manifest_text(plan: AlbumPlan) -> str:
    """Render a Markdown audit manifest for the proposed Google album."""
    lines = [
        "# Google Photos Album Upload Manifest",
        "",
        f"- Album: {plan.title}",
        f"- Source: `{plan.root}`",
        f"- Photographs: {plan.photo_count}",
        f"- Original-quality bytes: {plan.total_bytes}",
    ]
    for group in plan.groups:
        lines.extend(
            [
                "",
                f"## {group.heading}",
                "",
                f"- Source folder: `{group.folder_name}`",
                "- Files:",
            ]
        )
        for photo in group.photos:
            lines.append(f'  - `{photo.filename}`: {photo.description}')
    lines.append("")
    return "\n".join(lines)


def sha256_file(path: Path) -> str:
    """Hash a source file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _journal_plan(plan: AlbumPlan) -> list[dict[str, Any]]:
    return [
        {
            "key": group.key,
            "heading": group.heading,
            "photos": [
                {
                    "key": photo.key,
                    "filename": photo.filename,
                    "description": photo.description,
                    "size": photo.source.stat().st_size,
                    "sha256": sha256_file(photo.source),
                }
                for photo in group.photos
            ],
        }
        for group in plan.groups
    ]


class UploadJournal:
    """Atomic, non-secret record of confirmed and uncertain upload state."""

    def __init__(self, path: Path, plan: AlbumPlan, data: dict[str, Any]) -> None:
        self.path = path
        self.plan = plan
        self.data = data

    @classmethod
    def open_or_create(cls, path: Path, plan: AlbumPlan) -> UploadJournal:
        expanded = path.expanduser()
        if expanded.is_symlink():
            raise GooglePhotosError(f"upload journal must not be a symlink: {path}")
        resolved = expanded.resolve()
        expected_plan = _journal_plan(plan)
        if resolved.exists():
            try:
                data = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise GooglePhotosError(f"could not read upload journal: {resolved}") from error
            if not isinstance(data, dict) or data.get("version") != JOURNAL_VERSION:
                raise GooglePhotosError("unsupported or invalid upload journal version")
            if data.get("root") != str(plan.root) or data.get("title") != plan.title:
                raise GooglePhotosError("upload journal does not match the source root and album title")
            if data.get("plan") != expected_plan:
                raise GooglePhotosError(
                    "upload journal does not match the current files or album plan; "
                    "source content may have changed"
                )
            return cls(resolved, plan, data)

        data = {
            "version": JOURNAL_VERSION,
            "root": str(plan.root),
            "title": plan.title,
            "plan": expected_plan,
            "album": None,
            "confirmed_headings": {},
            "confirmed_media": {},
            "uncertain": None,
        }
        journal = cls(resolved, plan, data)
        journal.save()
        return journal

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(self.data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    @property
    def uncertain(self) -> dict[str, Any] | None:
        value = self.data.get("uncertain")
        return value if isinstance(value, dict) else None

    def set_uncertain(self, operation: dict[str, Any]) -> None:
        self.data["uncertain"] = operation
        self.save()

    def set_album(self, album_id: str, product_url: str) -> None:
        self.data["album"] = {"id": album_id, "product_url": product_url}
        self.data["uncertain"] = None
        self.save()

    def confirm_heading(self, key: str, enrichment_id: str) -> None:
        self.data["confirmed_headings"][key] = enrichment_id
        self.data["uncertain"] = None
        self.save()

    def confirm_media(self, key: str, media_id: str, product_url: str) -> None:
        self.data["confirmed_media"][key] = {
            "id": media_id,
            "product_url": product_url,
        }
        self.data["uncertain"] = None
        self.save()

    def resolve_uncertain(
        self,
        decision: str,
        *,
        remote_ids: Sequence[str] = (),
        product_url: str = "",
    ) -> None:
        operation = self.uncertain
        if operation is None:
            raise GooglePhotosError("the upload journal has no uncertain operation")
        if decision == "pending":
            self.data["uncertain"] = None
            self.save()
            return
        if decision != "completed":
            raise GooglePhotosError("uncertain resolution must be completed or pending")
        kind = operation.get("kind")
        keys = operation.get("keys", [])
        if kind == "album":
            if len(remote_ids) != 1 or not product_url:
                raise GooglePhotosError(
                    "completed album resolution requires one remote ID and --resolved-url"
                )
            self.set_album(remote_ids[0], product_url)
        elif kind == "heading":
            if len(remote_ids) != 1 or len(keys) != 1:
                raise GooglePhotosError("completed heading resolution requires one remote ID")
            self.confirm_heading(keys[0], remote_ids[0])
        elif kind == "media":
            if len(remote_ids) != len(keys):
                raise GooglePhotosError(
                    "completed media resolution requires one remote ID for every uncertain item"
                )
            for key, remote_id in zip(keys, remote_ids, strict=True):
                self.confirm_media(key, remote_id, "")
        elif kind == "upload_bytes":
            raise GooglePhotosError(
                "an uncertain byte upload cannot be marked completed because its token "
                "was not received; inspect the journal and resolve it as pending"
            )
        else:
            raise GooglePhotosError(f"unknown uncertain operation kind: {kind!r}")


class RequestsTransport:
    """HTTP transport backed by a Google AuthorizedSession."""

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        timeout: float = 60.0,
    ) -> HttpResponse:
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                data=data,
                timeout=timeout,
            )
        except requests.ConnectTimeout as error:
            raise TransportFailure(
                "connection timed out before a response", may_have_been_accepted=False
            ) from error
        except (requests.ReadTimeout, requests.ConnectionError) as error:
            raise TransportFailure(
                "connection failed after the request may have been sent",
                may_have_been_accepted=True,
            ) from error
        except requests.RequestException as error:
            raise TransportFailure(str(error), may_have_been_accepted=True) from error
        return HttpResponse(
            status_code=response.status_code,
            body=response.content,
            headers=dict(response.headers),
        )


class KeyringCredentialStore:
    """Store refreshable OAuth credentials in the operating-system keyring."""

    service_name = "photo-tools-google-photos"

    def get(self, account: str) -> str | None:
        import keyring

        return keyring.get_password(self.service_name, account)

    def set(self, account: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service_name, account, value)


class InstalledAppAuthorizer:
    """Authorize the app and retain refresh credentials only in the OS keyring."""

    def __init__(self, store: CredentialStore | None = None) -> None:
        self.store = store or KeyringCredentialStore()

    def authorized_transport(self, client_config_path: Path) -> RequestsTransport:
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        config_path = client_config_path.expanduser().resolve(strict=True)
        repo = repository_root()
        if _inside(config_path, repo):
            raise GooglePhotosError(
                "OAuth client configuration must be stored outside the repository"
            )
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            installed = config["installed"]
            client_id = installed["client_id"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise GooglePhotosError("invalid installed-application OAuth configuration") from error
        account = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
        try:
            stored = self.store.get(account)
        except Exception as error:
            raise GooglePhotosError("could not read OAuth credentials from the OS keyring") from error
        credentials: Credentials | None = None
        if stored:
            try:
                info = json.loads(stored)
                credentials = Credentials.from_authorized_user_info(info, OAUTH_SCOPES)
            except (ValueError, TypeError, json.JSONDecodeError):
                credentials = None
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as error:
                raise GooglePhotosError("could not refresh Google authorization") from error
        if credentials is None or not credentials.valid:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(config_path), scopes=list(OAUTH_SCOPES)
                )
                credentials = flow.run_local_server(port=0)
            except Exception as error:
                raise GooglePhotosError("Google authorization did not complete") from error
        try:
            self.store.set(account, credentials.to_json())
        except Exception as error:
            raise GooglePhotosError("could not store OAuth credentials in the OS keyring") from error
        return RequestsTransport(AuthorizedSession(credentials))


class GooglePhotosClient:
    """Small REST client with conservative mutation retry behavior."""

    def __init__(
        self,
        transport: HttpTransport,
        *,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.transport = transport
        self.max_attempts = max_attempts
        self.sleep = sleep

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        mutation: bool,
    ) -> HttpResponse:
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.transport.request(
                    method,
                    url,
                    headers=headers,
                    json_body=json_body,
                    data=data,
                )
            except TransportFailure as error:
                if error.may_have_been_accepted and mutation:
                    raise AmbiguousRequestError(redact(str(error))) from error
                if attempt == self.max_attempts:
                    raise ConfirmedRequestError(redact(str(error))) from error
                self.sleep(2 ** (attempt - 1))
                continue
            if response.status_code == 429 and attempt < self.max_attempts:
                self.sleep(2 ** (attempt - 1))
                continue
            if 200 <= response.status_code < 300:
                return response
            detail = redact(response.text)[:500]
            message = f"Google Photos returned HTTP {response.status_code}: {detail}"
            if mutation and response.status_code >= 500:
                raise AmbiguousRequestError(message)
            raise ConfirmedRequestError(message)
        raise AssertionError("unreachable retry loop")

    def create_album(self, title: str) -> tuple[str, str]:
        response = self._request(
            "POST",
            f"{API_BASE}/albums",
            json_body={"album": {"title": title}},
            mutation=True,
        ).json()
        album_id = response.get("id")
        product_url = response.get("productUrl")
        if not isinstance(album_id, str) or not isinstance(product_url, str):
            raise ConfirmedRequestError("album creation response omitted its ID or URL")
        return album_id, product_url

    def get_album(self, album_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"{API_BASE}/albums/{album_id}", mutation=False
        ).json()

    def add_heading(self, album_id: str, heading: str) -> str:
        response = self._request(
            "POST",
            f"{API_BASE}/albums/{album_id}:addEnrichment",
            json_body={
                "newEnrichmentItem": {"textEnrichment": {"text": heading}},
                "albumPosition": {"position": "LAST_IN_ALBUM"},
            },
            mutation=True,
        ).json()
        enrichment = response.get("enrichmentItem", {})
        enrichment_id = enrichment.get("id") if isinstance(enrichment, dict) else None
        if not isinstance(enrichment_id, str):
            raise ConfirmedRequestError("heading response omitted its enrichment ID")
        return enrichment_id

    def upload_bytes(self, photo: AlbumPhoto) -> str:
        response = self._request(
            "POST",
            UPLOAD_URL,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Goog-Upload-Content-Type": "image/jpeg",
                "X-Goog-Upload-Protocol": "raw",
            },
            data=photo.source.read_bytes(),
            mutation=True,
        )
        token = response.text.strip()
        if not token:
            raise ConfirmedRequestError("byte upload response omitted its upload token")
        return token

    def create_media(
        self,
        album_id: str,
        photos: Sequence[AlbumPhoto],
        upload_tokens: Sequence[str],
    ) -> list[dict[str, str]]:
        if len(photos) != len(upload_tokens) or len(photos) > MAX_BATCH_ITEMS:
            raise GooglePhotosError("invalid Google Photos media batch")
        body = {
            "albumId": album_id,
            "albumPosition": {"position": "LAST_IN_ALBUM"},
            "newMediaItems": [
                {
                    "description": photo.description,
                    "simpleMediaItem": {
                        "fileName": photo.filename,
                        "uploadToken": token,
                    },
                }
                for photo, token in zip(photos, upload_tokens, strict=True)
            ],
        }
        response = self._request(
            "POST",
            f"{API_BASE}/mediaItems:batchCreate",
            json_body=body,
            mutation=True,
        ).json()
        results = response.get("newMediaItemResults")
        if not isinstance(results, list) or len(results) != len(photos):
            raise ConfirmedRequestError("media creation response had an unexpected result count")
        parsed: list[dict[str, str]] = []
        failures: list[str] = []
        for photo, result in zip(photos, results, strict=True):
            if not isinstance(result, dict):
                failures.append(f"{photo.key}: invalid result")
                parsed.append({})
                continue
            status = result.get("status", {})
            code = status.get("code", 0) if isinstance(status, dict) else -1
            item = result.get("mediaItem", {})
            media_id = item.get("id") if isinstance(item, dict) else None
            product_url = item.get("productUrl", "") if isinstance(item, dict) else ""
            if code != 0 or not isinstance(media_id, str):
                message = status.get("message", "creation failed") if isinstance(status, dict) else "creation failed"
                failures.append(f"{photo.key}: {redact(str(message))}")
                parsed.append({})
            else:
                parsed.append({"id": media_id, "product_url": str(product_url)})
        if failures:
            error = ConfirmedRequestError("media creation failed:\n" + "\n".join(failures))
            setattr(error, "partial_results", parsed)
            raise error
        return parsed


def upload_album(
    plan: AlbumPlan,
    journal: UploadJournal,
    client: GooglePhotosClient,
) -> str:
    """Create or resume one ordered app-created album."""
    if journal.uncertain is not None:
        raise GooglePhotosError(
            "upload journal contains an uncertain operation; inspect Google Photos "
            "and resolve it before resuming"
        )

    album = journal.data.get("album")
    if album is None:
        try:
            album_id, product_url = client.create_album(plan.title)
        except KeyboardInterrupt as error:
            journal.set_uncertain({"kind": "album", "keys": [plan.title]})
            raise AmbiguousRequestError("interrupted during album creation") from error
        except AmbiguousRequestError:
            journal.set_uncertain({"kind": "album", "keys": [plan.title]})
            raise
        journal.set_album(album_id, product_url)
    else:
        album_id = album.get("id")
        product_url = album.get("product_url")
        if not isinstance(album_id, str) or not isinstance(product_url, str):
            raise GooglePhotosError("upload journal contains an invalid album record")
        remote_album = client.get_album(album_id)
        if remote_album.get("id") != album_id:
            raise GooglePhotosError("recorded application-created album is no longer accessible")

    for group in plan.groups:
        if group.key not in journal.data["confirmed_headings"]:
            try:
                enrichment_id = client.add_heading(album_id, group.heading)
            except KeyboardInterrupt as error:
                journal.set_uncertain({"kind": "heading", "keys": [group.key]})
                raise AmbiguousRequestError("interrupted while adding a heading") from error
            except AmbiguousRequestError:
                journal.set_uncertain({"kind": "heading", "keys": [group.key]})
                raise
            journal.confirm_heading(group.key, enrichment_id)

        pending = [
            photo
            for photo in group.photos
            if photo.key not in journal.data["confirmed_media"]
        ]
        for offset in range(0, len(pending), MAX_BATCH_ITEMS):
            batch = pending[offset : offset + MAX_BATCH_ITEMS]
            tokens: list[str] = []
            for photo in batch:
                try:
                    tokens.append(client.upload_bytes(photo))
                except KeyboardInterrupt as error:
                    journal.set_uncertain(
                        {"kind": "upload_bytes", "keys": [photo.key]}
                    )
                    raise AmbiguousRequestError(
                        "interrupted while uploading photograph bytes"
                    ) from error
                except AmbiguousRequestError:
                    journal.set_uncertain({"kind": "upload_bytes", "keys": [photo.key]})
                    raise
            try:
                results = client.create_media(album_id, batch, tokens)
            except KeyboardInterrupt as error:
                journal.set_uncertain(
                    {"kind": "media", "keys": [photo.key for photo in batch]}
                )
                raise AmbiguousRequestError(
                    "interrupted while creating Google Photos media items"
                ) from error
            except ConfirmedRequestError as error:
                partial = getattr(error, "partial_results", [])
                for photo, result in zip(batch, partial, strict=False):
                    if result:
                        journal.confirm_media(
                            photo.key, result["id"], result["product_url"]
                        )
                raise
            except AmbiguousRequestError:
                journal.set_uncertain(
                    {"kind": "media", "keys": [photo.key for photo in batch]}
                )
                raise
            for photo, result in zip(batch, results, strict=True):
                journal.confirm_media(photo.key, result["id"], result["product_url"])
    return product_url
