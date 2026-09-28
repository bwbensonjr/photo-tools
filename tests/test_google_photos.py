"""Google Photos planning, transport, ordering, and recovery tests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import pytest

import photo_tools.google_photos as google_photos
from photo_tools.google_photos import (
    API_BASE,
    AmbiguousRequestError,
    ConfirmedRequestError,
    GooglePhotosClient,
    GooglePhotosError,
    HttpResponse,
    InstalledAppAuthorizer,
    TransportFailure,
    UploadJournal,
    album_manifest_text,
    build_album_plan,
    redact,
    render_album_preview,
    upload_album,
)
from photo_tools.scan_metadata import build_plan

from conftest import make_folder


class FakeTransport:
    """Scripted HTTP transport that records request order and content."""

    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

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
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json_body,
                "data": data,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def response(status: int, body: dict[str, Any] | str) -> HttpResponse:
    encoded = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    return HttpResponse(status, encoded, {})


def media_response(*ids: str) -> HttpResponse:
    return response(
        200,
        {
            "newMediaItemResults": [
                {
                    "status": {"code": 0},
                    "mediaItem": {
                        "id": media_id,
                        "productUrl": f"https://photos.example/{media_id}",
                    },
                }
                for media_id in ids
            ]
        },
    )


def two_group_plan(tmp_path: Path):
    make_folder(tmp_path, "1997-03-06-A-first", ["b.jpg", "a.jpg"])
    make_folder(tmp_path, "1997-03-06-B-second", ["c.jpg"])
    scan_plan = build_plan(tmp_path)
    return build_album_plan(scan_plan, scan_plan.entries, title="Family scans")


def test_preview_and_manifest_keep_duplicate_date_groups_contiguous(tmp_path: Path) -> None:
    plan = two_group_plan(tmp_path)

    preview = render_album_preview(plan)
    manifest = album_manifest_text(plan)

    assert preview.index("1997-03-06 - A first") < preview.index("a.jpg")
    assert preview.index("a.jpg") < preview.index("b.jpg")
    assert preview.index("b.jpg") < preview.index("1997-03-06 - B second")
    assert 'a.jpg -> description "A first"' in preview
    assert "same-date groups: 1997-03-06 (2 folders)" in preview
    assert "no OAuth flow or Google Photos request was performed" in preview
    assert manifest.index("## 1997-03-06 - A first") < manifest.index("## 1997-03-06 - B second")


def test_filtered_album_plan_preserves_complete_plan_order(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])
    make_folder(tmp_path, "1997-03-06-B-second", ["b.jpg"])
    scan_plan = build_plan(tmp_path)

    album = build_album_plan(
        scan_plan,
        scan_plan.selected({"1997-03-06-B-second"}),
        title="Filtered",
    )

    assert [group.folder_name for group in album.groups] == ["1997-03-06-B-second"]
    assert album.groups[0].photos[0].description == "B second"


def test_album_item_limit_is_preflighted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_folder(tmp_path, "1997-03-06-A", ["a.jpg", "b.jpg"])
    scan_plan = build_plan(tmp_path)
    monkeypatch.setattr(google_photos, "MAX_ALBUM_ITEMS", 1)

    with pytest.raises(GooglePhotosError, match="limits albums"):
        build_album_plan(scan_plan, scan_plan.entries, title="Too many")


def test_upload_orders_heading_then_native_descriptions_and_batches(tmp_path: Path) -> None:
    plan = two_group_plan(tmp_path)
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "productUrl": "https://photos.example/album-1"}),
            response(200, {"enrichmentItem": {"id": "heading-1"}}),
            response(200, "token-a"),
            response(200, "token-b"),
            media_response("media-a", "media-b"),
            response(200, {"enrichmentItem": {"id": "heading-2"}}),
            response(200, "token-c"),
            media_response("media-c"),
        ]
    )

    url = upload_album(plan, journal, GooglePhotosClient(transport, sleep=lambda _: None))

    assert url == "https://photos.example/album-1"
    urls = [request["url"] for request in transport.requests]
    assert urls == [
        f"{API_BASE}/albums",
        f"{API_BASE}/albums/album-1:addEnrichment",
        google_photos.UPLOAD_URL,
        google_photos.UPLOAD_URL,
        f"{API_BASE}/mediaItems:batchCreate",
        f"{API_BASE}/albums/album-1:addEnrichment",
        google_photos.UPLOAD_URL,
        f"{API_BASE}/mediaItems:batchCreate",
    ]
    first_batch = transport.requests[4]["json"]
    assert [item["simpleMediaItem"]["fileName"] for item in first_batch["newMediaItems"]] == ["a.jpg", "b.jpg"]
    assert [item["description"] for item in first_batch["newMediaItems"]] == ["A first", "A first"]
    assert first_batch["albumPosition"] == {"position": "LAST_IN_ALBUM"}


def test_resume_skips_confirmed_remote_work_and_rejects_changed_source(tmp_path: Path) -> None:
    plan = two_group_plan(tmp_path)
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, plan)
    first_transport = FakeTransport(
        [
            response(200, {"id": "album-1", "productUrl": "https://photos.example/album-1"}),
            response(200, {"enrichmentItem": {"id": "heading-1"}}),
            response(200, "token-a"),
            response(200, "token-b"),
            media_response("media-a", "media-b"),
            response(200, {"enrichmentItem": {"id": "heading-2"}}),
            response(400, {"error": {"message": "rejected before acceptance"}}),
        ]
    )
    with pytest.raises(ConfirmedRequestError):
        upload_album(plan, journal, GooglePhotosClient(first_transport, sleep=lambda _: None))

    resumed = UploadJournal.open_or_create(journal_path, plan)
    second_transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(200, "token-c"),
            media_response("media-c"),
        ]
    )
    upload_album(plan, resumed, GooglePhotosClient(second_transport, sleep=lambda _: None))

    assert [request["url"] for request in second_transport.requests] == [
        f"{API_BASE}/albums/album-1",
        google_photos.UPLOAD_URL,
        f"{API_BASE}/mediaItems:batchCreate",
    ]
    assert len(resumed.data["confirmed_media"]) == 3

    plan.groups[0].photos[0].source.write_bytes(b"changed")
    with pytest.raises(GooglePhotosError, match="source content may have changed"):
        UploadJournal.open_or_create(journal_path, plan)


def test_ambiguous_media_creation_stops_resume_until_explicit_resolution(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-A", ["a.jpg"])
    scan_plan = build_plan(tmp_path)
    plan = build_album_plan(scan_plan, scan_plan.entries, title="Family scans")
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "productUrl": "https://photos.example/album-1"}),
            response(200, {"enrichmentItem": {"id": "heading-1"}}),
            response(200, "token-a"),
            TransportFailure("read timeout", may_have_been_accepted=True),
        ]
    )

    with pytest.raises(AmbiguousRequestError):
        upload_album(plan, journal, GooglePhotosClient(transport, sleep=lambda _: None))
    assert journal.uncertain == {"kind": "media", "keys": ["1997-03-06-A/a.jpg"]}

    untouched = FakeTransport([])
    with pytest.raises(GooglePhotosError, match="resolve it before resuming"):
        upload_album(plan, journal, GooglePhotosClient(untouched))
    assert untouched.requests == []

    journal.resolve_uncertain("pending")
    assert journal.uncertain is None


def test_rate_limit_retries_but_server_error_is_ambiguous(tmp_path: Path) -> None:
    photo_plan = two_group_plan(tmp_path)
    photo = photo_plan.groups[0].photos[0]
    sleeps: list[float] = []
    retry_transport = FakeTransport([response(429, "slow down"), response(200, "token-a")])
    client = GooglePhotosClient(retry_transport, sleep=sleeps.append)

    assert client.upload_bytes(photo) == "token-a"
    assert sleeps == [1]

    server_transport = FakeTransport([response(500, "server error")])
    with pytest.raises(AmbiguousRequestError, match="HTTP 500"):
        GooglePhotosClient(server_transport, sleep=lambda _: None).create_album("Family")
    assert len(server_transport.requests) == 1


def test_interruption_records_uncertain_operation(tmp_path: Path) -> None:
    plan = two_group_plan(tmp_path)
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    transport = FakeTransport([KeyboardInterrupt()])

    with pytest.raises(AmbiguousRequestError, match="interrupted"):
        upload_album(plan, journal, GooglePhotosClient(transport))
    assert journal.uncertain == {"kind": "album", "keys": ["Family scans"]}


def test_redaction_and_journal_exclude_oauth_secrets(tmp_path: Path) -> None:
    secret = "client-secret-value"
    access = "access-token-value"
    refresh = "refresh-token-value"
    message = (
        f'Authorization: Bearer {access} "client_secret": "{secret}" '
        f'refresh_token={refresh}'
    )

    cleaned = redact(message, [secret, access, refresh])

    assert secret not in cleaned
    assert access not in cleaned
    assert refresh not in cleaned
    plan = two_group_plan(tmp_path)
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    journal_text = journal.path.read_text(encoding="utf-8")
    assert secret not in journal_text
    assert access not in journal_text
    assert refresh not in journal_text


class MemoryCredentialStore:
    def __init__(self, account: str, value: str) -> None:
        self.values = {account: value}

    def get(self, account: str) -> str | None:
        return self.values.get(account)

    def set(self, account: str, value: str) -> None:
        self.values[account] = value


def test_installed_app_authorizer_reads_refresh_credentials_from_store_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client_id = "test-client.apps.googleusercontent.com"
    client_secret = "-".join(("client", "secret", "value"))
    access_token = "-".join(("access", "token", "value"))
    refresh_token = "-".join(("refresh", "token", "value"))
    config = tmp_path / "external-client.json"
    config.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    account = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
    stored = json.dumps(
        {
            "token": access_token,
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": list(google_photos.OAUTH_SCOPES),
            "expiry": "2099-01-01T00:00:00Z",
        }
    )
    store = MemoryCredentialStore(account, stored)

    transport = InstalledAppAuthorizer(store).authorized_transport(config)

    assert isinstance(transport, google_photos.RequestsTransport)
    assert capsys.readouterr().out == ""
    source_root = google_photos.repository_root() / "src"
    repository_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in source_root.rglob("*")
        if path.is_file()
    )
    assert client_secret not in repository_text
    assert access_token not in repository_text
    assert refresh_token not in repository_text


def test_authorizer_rejects_client_configuration_inside_repository() -> None:
    config = google_photos.repository_root() / "pyproject.toml"
    with pytest.raises(GooglePhotosError, match="outside the repository"):
        InstalledAppAuthorizer(MemoryCredentialStore("unused", "unused")).authorized_transport(config)
