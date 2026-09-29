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
    AlbumPosition,
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
    heading_position,
    next_pending_media_batch,
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
    assert "no OAuth flow or Google Photos request was performed" not in preview
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


def test_album_position_validation_and_json() -> None:
    assert AlbumPosition.first().to_json() == {"position": "FIRST_IN_ALBUM"}
    assert AlbumPosition.after_media("media-1").to_json() == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-1",
    }
    assert AlbumPosition.after_enrichment("heading-1").to_json() == {
        "position": "AFTER_ENRICHMENT_ITEM",
        "relativeEnrichmentItemId": "heading-1",
    }

    invalid = [
        ("LAST_IN_ALBUM", None, None),
        ("FIRST_IN_ALBUM", "media-1", None),
        ("AFTER_MEDIA_ITEM", None, None),
        ("AFTER_MEDIA_ITEM", "media-1", "heading-1"),
        ("AFTER_ENRICHMENT_ITEM", None, None),
    ]
    for position, media_id, enrichment_id in invalid:
        with pytest.raises(GooglePhotosError, match="invalid Google Photos album position"):
            AlbumPosition(position, media_id, enrichment_id)


def test_album_media_ids_pages_in_remote_order() -> None:
    transport = FakeTransport(
        [
            response(
                200,
                {
                    "mediaItems": [{"id": "media-a"}],
                    "nextPageToken": "page-2",
                },
            ),
            response(200, {"mediaItems": [{"id": "media-b"}]}),
        ]
    )

    result = GooglePhotosClient(transport, sleep=lambda _: None).album_media_ids(
        "album-1"
    )

    assert result == ["media-a", "media-b"]
    assert [request["json"] for request in transport.requests] == [
        {"albumId": "album-1", "pageSize": 100},
        {"albumId": "album-1", "pageSize": 100, "pageToken": "page-2"},
    ]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"mediaItems": "invalid"}, "invalid mediaItems"),
        ({"mediaItems": [{}]}, "without an ID"),
        ({"nextPageToken": ""}, "invalid page token"),
    ],
)
def test_album_media_ids_rejects_malformed_responses(
    payload: dict[str, Any], message: str
) -> None:
    client = GooglePhotosClient(FakeTransport([response(200, payload)]))

    with pytest.raises(ConfirmedRequestError, match=message):
        client.album_media_ids("album-1")


def test_album_media_ids_reports_confirmed_http_failure() -> None:
    client = GooglePhotosClient(FakeTransport([response(400, "rejected")]))

    with pytest.raises(ConfirmedRequestError, match="HTTP 400"):
        client.album_media_ids("album-1")


def test_insertion_planner_derives_first_middle_and_last_heading_positions(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-First", ["a.jpg"])
    make_folder(tmp_path, "1997-02-01-Second", ["b.jpg"])
    make_folder(tmp_path, "1997-03-01-Third", ["c.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)

    assert heading_position(plan, plan.groups[0], journal) == AlbumPosition.first()
    journal.confirm_media(plan.groups[0].photos[0].key, "media-a", "")
    assert heading_position(plan, plan.groups[1], journal) == AlbumPosition.after_media(
        "media-a"
    )
    journal.confirm_media(plan.groups[1].photos[0].key, "media-b", "")
    assert heading_position(plan, plan.groups[2], journal) == AlbumPosition.after_media(
        "media-b"
    )


def test_pending_media_planner_handles_prefix_and_interior_gaps(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    group = plan.groups[0]
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    journal.confirm_heading(group.key, "heading-1")

    initial = next_pending_media_batch(group, journal)
    assert initial is not None
    assert [photo.filename for photo in initial.photos] == [
        "a.jpg",
        "b.jpg",
        "c.jpg",
        "d.jpg",
    ]
    assert initial.position == AlbumPosition.after_enrichment("heading-1")

    journal.confirm_media(group.photos[0].key, "media-a", "")
    journal.confirm_media(group.photos[2].key, "media-c", "")
    interior = next_pending_media_batch(group, journal)
    assert interior is not None
    assert [photo.filename for photo in interior.photos] == ["b.jpg"]
    assert interior.position == AlbumPosition.after_media("media-a")

    journal.confirm_media(group.photos[1].key, "media-b", "")
    suffix = next_pending_media_batch(group, journal)
    assert suffix is not None
    assert [photo.filename for photo in suffix.photos] == ["d.jpg"]
    assert suffix.position == AlbumPosition.after_media("media-c")


def test_pending_media_planner_splits_large_run_at_batch_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg", "b.jpg", "c.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    group = plan.groups[0]
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    journal.confirm_heading(group.key, "heading-1")
    monkeypatch.setattr(google_photos, "MAX_BATCH_ITEMS", 2)

    batch = next_pending_media_batch(group, journal)

    assert batch is not None
    assert [photo.filename for photo in batch.photos] == ["a.jpg", "b.jpg"]


def test_uncertain_media_position_is_audited_and_anchor_is_recomputed(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg", "b.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    group = plan.groups[0]
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    journal.confirm_heading(group.key, "heading-1")
    position = AlbumPosition.after_enrichment("heading-1")
    journal.set_uncertain(
        {
            "kind": "media",
            "keys": [group.photos[0].key],
            "position": position.to_json(),
        }
    )

    journal.resolve_uncertain("completed", remote_ids=["media-a"])
    resumed = next_pending_media_batch(group, journal)

    assert resumed is not None
    assert [photo.filename for photo in resumed.photos] == ["b.jpg"]
    assert resumed.position == AlbumPosition.after_media("media-a")


def test_version_one_uncertain_record_without_position_remains_readable(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, plan)
    journal.set_uncertain({"kind": "media", "keys": [plan.groups[0].photos[0].key]})

    reopened = UploadJournal.open_or_create(journal_path, plan)
    reopened.resolve_uncertain("pending")

    assert reopened.uncertain is None


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

    started: list[str] = []
    url = upload_album(
        plan,
        journal,
        GooglePhotosClient(transport, sleep=lambda _: None),
        on_folder_start=started.append,
    )

    assert url == "https://photos.example/album-1"
    assert started == ["1997-03-06-A-first", "1997-03-06-B-second"]
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
    assert transport.requests[1]["json"]["albumPosition"] == {
        "position": "FIRST_IN_ALBUM"
    }
    assert first_batch["albumPosition"] == {
        "position": "AFTER_ENRICHMENT_ITEM",
        "relativeEnrichmentItemId": "heading-1",
    }
    assert transport.requests[5]["json"]["albumPosition"] == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-b",
    }
    assert transport.requests[7]["json"]["albumPosition"] == {
        "position": "AFTER_ENRICHMENT_ITEM",
        "relativeEnrichmentItemId": "heading-2",
    }


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
            response(
                200,
                {"mediaItems": [{"id": "media-a"}, {"id": "media-b"}]},
            ),
            response(200, "token-c"),
            media_response("media-c"),
        ]
    )
    resumed_started: list[str] = []
    upload_album(
        plan,
        resumed,
        GooglePhotosClient(second_transport, sleep=lambda _: None),
        on_folder_start=resumed_started.append,
    )

    assert resumed_started == ["1997-03-06-B-second"]
    assert [request["url"] for request in second_transport.requests] == [
        f"{API_BASE}/albums/album-1",
        f"{API_BASE}/mediaItems:search",
        google_photos.UPLOAD_URL,
        f"{API_BASE}/mediaItems:batchCreate",
    ]
    assert len(resumed.data["confirmed_media"]) == 3

    complete_transport = FakeTransport(
        [response(200, {"id": "album-1", "title": "Family scans"})]
    )
    complete_started: list[str] = []
    upload_album(
        plan,
        UploadJournal.open_or_create(journal_path, plan),
        GooglePhotosClient(complete_transport, sleep=lambda _: None),
        on_folder_start=complete_started.append,
    )
    assert complete_started == []
    assert [request["url"] for request in complete_transport.requests] == [
        f"{API_BASE}/albums/album-1"
    ]

    plan.groups[0].photos[0].source.write_bytes(b"changed")
    with pytest.raises(GooglePhotosError, match="source content may have changed"):
        UploadJournal.open_or_create(journal_path, plan)


def test_resume_accepts_new_folder_and_uploads_only_its_photos(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-06-01-First", ["a.jpg"])
    make_folder(tmp_path, "1997-08-01-Third", ["c.jpg"])
    initial_scan = build_plan(tmp_path)
    initial_plan = build_album_plan(
        initial_scan, initial_scan.entries, title="Family scans"
    )
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, initial_plan)
    journal.set_album("album-1", "https://photos.example/album-1")
    for group in initial_plan.groups:
        journal.confirm_heading(group.key, f"heading-{group.key}")
        for photo in group.photos:
            journal.confirm_media(photo.key, f"media-{photo.key}", "")

    make_folder(tmp_path, "1997-07-01-Second", ["b.jpg"])
    extended_scan = build_plan(tmp_path)
    extended_plan = build_album_plan(
        extended_scan, extended_scan.entries, title="Family scans"
    )
    resumed = UploadJournal.open_or_create(journal_path, extended_plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(
                200,
                {
                    "mediaItems": [
                        {"id": "media-1997-06-01-First/a.jpg"},
                        {"id": "media-1997-08-01-Third/c.jpg"},
                    ]
                },
            ),
            response(200, {"enrichmentItem": {"id": "heading-second"}}),
            response(200, "token-b"),
            media_response("media-b"),
        ]
    )
    started: list[str] = []

    upload_album(
        extended_plan,
        resumed,
        GooglePhotosClient(transport, sleep=lambda _: None),
        on_folder_start=started.append,
    )

    assert started == ["1997-07-01-Second"]
    assert len(resumed.data["confirmed_headings"]) == 3
    assert len(resumed.data["confirmed_media"]) == 3
    assert [request["url"] for request in transport.requests] == [
        f"{API_BASE}/albums/album-1",
        f"{API_BASE}/mediaItems:search",
        f"{API_BASE}/albums/album-1:addEnrichment",
        google_photos.UPLOAD_URL,
        f"{API_BASE}/mediaItems:batchCreate",
    ]
    assert transport.requests[2]["json"]["albumPosition"] == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-1997-06-01-First/a.jpg",
    }
    assert transport.requests[4]["json"]["albumPosition"] == {
        "position": "AFTER_ENRICHMENT_ITEM",
        "relativeEnrichmentItemId": "heading-second",
    }


@pytest.mark.parametrize(
    "remote_ids",
    [
        ["media-a"],
        ["media-a", "media-a", "media-c"],
        ["media-a", "media-c", "media-extra"],
        ["media-c", "media-a"],
    ],
)
def test_incremental_upload_refuses_remote_order_drift_before_mutation(
    tmp_path: Path, remote_ids: list[str]
) -> None:
    make_folder(tmp_path, "1997-01-01-First", ["a.jpg"])
    make_folder(tmp_path, "1997-03-01-Third", ["c.jpg"])
    initial_scan = build_plan(tmp_path)
    initial_plan = build_album_plan(
        initial_scan, initial_scan.entries, title="Family scans"
    )
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, initial_plan)
    journal.set_album("album-1", "https://photos.example/album-1")
    for group, media_id in zip(initial_plan.groups, ["media-a", "media-c"], strict=True):
        journal.confirm_heading(group.key, f"heading-{media_id}")
        journal.confirm_media(group.photos[0].key, media_id, "")
    make_folder(tmp_path, "1997-02-01-Second", ["b.jpg"])
    extended_scan = build_plan(tmp_path)
    extended_plan = build_album_plan(
        extended_scan, extended_scan.entries, title="Family scans"
    )
    resumed = UploadJournal.open_or_create(journal_path, extended_plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(200, {"mediaItems": [{"id": item} for item in remote_ids]}),
        ]
    )

    with pytest.raises(GooglePhotosError, match="remote album order drift"):
        upload_album(
            extended_plan,
            resumed,
            GooglePhotosClient(transport, sleep=lambda _: None),
        )

    assert [request["url"] for request in transport.requests] == [
        f"{API_BASE}/albums/album-1",
        f"{API_BASE}/mediaItems:search",
    ]


def test_incremental_upload_inserts_new_first_group_at_album_beginning(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-02-01-Later", ["b.jpg"])
    initial_scan = build_plan(tmp_path)
    initial_plan = build_album_plan(
        initial_scan, initial_scan.entries, title="Family scans"
    )
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, initial_plan)
    journal.set_album("album-1", "https://photos.example/album-1")
    group = initial_plan.groups[0]
    journal.confirm_heading(group.key, "heading-b")
    journal.confirm_media(group.photos[0].key, "media-b", "")
    make_folder(tmp_path, "1997-01-01-Earlier", ["a.jpg"])
    extended_scan = build_plan(tmp_path)
    extended_plan = build_album_plan(
        extended_scan, extended_scan.entries, title="Family scans"
    )
    resumed = UploadJournal.open_or_create(journal_path, extended_plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(200, {"mediaItems": [{"id": "media-b"}]}),
            response(200, {"enrichmentItem": {"id": "heading-a"}}),
            response(200, "token-a"),
            media_response("media-a"),
        ]
    )

    upload_album(
        extended_plan,
        resumed,
        GooglePhotosClient(transport, sleep=lambda _: None),
    )

    assert transport.requests[2]["json"]["albumPosition"] == {
        "position": "FIRST_IN_ALBUM"
    }
    assert transport.requests[4]["json"]["albumPosition"] == {
        "position": "AFTER_ENRICHMENT_ITEM",
        "relativeEnrichmentItemId": "heading-a",
    }


def test_incremental_upload_orders_consecutive_new_groups_in_one_gap(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-First", ["a.jpg"])
    make_folder(tmp_path, "1997-04-01-Last", ["d.jpg"])
    initial_scan = build_plan(tmp_path)
    initial_plan = build_album_plan(
        initial_scan, initial_scan.entries, title="Family scans"
    )
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, initial_plan)
    journal.set_album("album-1", "https://photos.example/album-1")
    for group, media_id in zip(initial_plan.groups, ["media-a", "media-d"], strict=True):
        journal.confirm_heading(group.key, f"heading-{media_id}")
        journal.confirm_media(group.photos[0].key, media_id, "")
    make_folder(tmp_path, "1997-02-01-Second", ["b.jpg"])
    make_folder(tmp_path, "1997-03-01-Third", ["c.jpg"])
    extended_scan = build_plan(tmp_path)
    extended_plan = build_album_plan(
        extended_scan, extended_scan.entries, title="Family scans"
    )
    resumed = UploadJournal.open_or_create(journal_path, extended_plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(200, {"mediaItems": [{"id": "media-a"}, {"id": "media-d"}]}),
            response(200, {"enrichmentItem": {"id": "heading-b"}}),
            response(200, "token-b"),
            media_response("media-b"),
            response(200, {"enrichmentItem": {"id": "heading-c"}}),
            response(200, "token-c"),
            media_response("media-c"),
        ]
    )

    upload_album(
        extended_plan,
        resumed,
        GooglePhotosClient(transport, sleep=lambda _: None),
    )

    assert transport.requests[2]["json"]["albumPosition"] == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-a",
    }
    assert transport.requests[5]["json"]["albumPosition"] == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-b",
    }
    uploaded_bytes = [
        request["data"]
        for request in transport.requests
        if request["url"] == google_photos.UPLOAD_URL
    ]
    assert len(uploaded_bytes) == 2


def test_partial_media_results_resume_inside_existing_group(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg", "b.jpg", "c.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, plan)
    partial_response = response(
        200,
        {
            "newMediaItemResults": [
                {"status": {"code": 0}, "mediaItem": {"id": "media-a"}},
                {"status": {"code": 13, "message": "rejected"}},
                {"status": {"code": 0}, "mediaItem": {"id": "media-c"}},
            ]
        },
    )
    first_transport = FakeTransport(
        [
            response(200, {"id": "album-1", "productUrl": "https://photos.example/album-1"}),
            response(200, {"enrichmentItem": {"id": "heading-1"}}),
            response(200, "token-a"),
            response(200, "token-b"),
            response(200, "token-c"),
            partial_response,
        ]
    )
    with pytest.raises(ConfirmedRequestError, match="media creation failed"):
        upload_album(plan, journal, GooglePhotosClient(first_transport, sleep=lambda _: None))

    resumed = UploadJournal.open_or_create(journal_path, plan)
    second_transport = FakeTransport(
        [
            response(200, {"id": "album-1", "title": "Family scans"}),
            response(200, {"mediaItems": [{"id": "media-a"}, {"id": "media-c"}]}),
            response(200, "token-b-2"),
            media_response("media-b"),
        ]
    )

    upload_album(
        plan,
        resumed,
        GooglePhotosClient(second_transport, sleep=lambda _: None),
    )

    assert second_transport.requests[3]["json"]["albumPosition"] == {
        "position": "AFTER_MEDIA_ITEM",
        "relativeMediaItemId": "media-a",
    }
    assert len(resumed.data["confirmed_media"]) == 3


def test_keyboard_interrupt_records_positioned_media_operation(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    journal = UploadJournal.open_or_create(tmp_path / "journal.json", plan)
    transport = FakeTransport(
        [
            response(200, {"id": "album-1", "productUrl": "https://photos.example/album-1"}),
            response(200, {"enrichmentItem": {"id": "heading-1"}}),
            response(200, "token-a"),
            KeyboardInterrupt(),
        ]
    )

    with pytest.raises(AmbiguousRequestError, match="interrupted"):
        upload_album(plan, journal, GooglePhotosClient(transport))

    assert journal.uncertain == {
        "kind": "media",
        "keys": ["1997-01-01-Group/a.jpg"],
        "position": {
            "position": "AFTER_ENRICHMENT_ITEM",
            "relativeEnrichmentItemId": "heading-1",
        },
    }


def test_completed_uncertain_media_resolution_is_not_reuploaded(
    tmp_path: Path,
) -> None:
    make_folder(tmp_path, "1997-01-01-Group", ["a.jpg"])
    scan = build_plan(tmp_path)
    plan = build_album_plan(scan, scan.entries, title="Family scans")
    journal_path = tmp_path / "journal.json"
    journal = UploadJournal.open_or_create(journal_path, plan)
    journal.set_album("album-1", "https://photos.example/album-1")
    group = plan.groups[0]
    journal.confirm_heading(group.key, "heading-1")
    journal.set_uncertain(
        {
            "kind": "media",
            "keys": [group.photos[0].key],
            "position": AlbumPosition.after_enrichment("heading-1").to_json(),
        }
    )
    journal.resolve_uncertain("completed", remote_ids=["media-a"])
    transport = FakeTransport(
        [response(200, {"id": "album-1", "title": "Family scans"})]
    )

    upload_album(plan, journal, GooglePhotosClient(transport, sleep=lambda _: None))

    assert [request["url"] for request in transport.requests] == [
        f"{API_BASE}/albums/album-1"
    ]


def test_resume_rejects_new_photo_in_existing_folder(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "1997-06-01-First", ["a.jpg"])
    initial_scan = build_plan(tmp_path)
    initial_plan = build_album_plan(
        initial_scan, initial_scan.entries, title="Family scans"
    )
    journal_path = tmp_path / "journal.json"
    UploadJournal.open_or_create(journal_path, initial_plan)

    (folder / "b.jpg").write_bytes(b"new photo")
    changed_scan = build_plan(tmp_path)
    changed_plan = build_album_plan(
        changed_scan, changed_scan.entries, title="Family scans"
    )

    with pytest.raises(GooglePhotosError, match="source content may have changed"):
        UploadJournal.open_or_create(journal_path, changed_plan)


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
    assert journal.uncertain == {
        "kind": "media",
        "keys": ["1997-03-06-A/a.jpg"],
        "position": {
            "position": "AFTER_ENRICHMENT_ITEM",
            "relativeEnrichmentItemId": "heading-1",
        },
    }

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


def test_authorizer_reports_missing_client_configuration(tmp_path: Path) -> None:
    config = tmp_path / "missing-client.json"

    with pytest.raises(GooglePhotosError, match="OAuth client configuration not found"):
        InstalledAppAuthorizer(MemoryCredentialStore("unused", "unused")).authorized_transport(config)


def test_authorizer_reports_unreadable_client_configuration(tmp_path: Path) -> None:
    config = tmp_path / "client-directory"
    config.mkdir()

    with pytest.raises(GooglePhotosError, match="could not read OAuth client configuration"):
        InstalledAppAuthorizer(MemoryCredentialStore("unused", "unused")).authorized_transport(config)


def test_authorizer_reports_invalid_client_configuration(tmp_path: Path) -> None:
    config = tmp_path / "invalid-client.json"
    config.write_text("{}", encoding="utf-8")

    with pytest.raises(GooglePhotosError, match="invalid installed-application"):
        InstalledAppAuthorizer(MemoryCredentialStore("unused", "unused")).authorized_transport(config)
