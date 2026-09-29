"""Safe command-line behavior for Google Photos previews and uploads."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from photo_tools import google_photos_cli
from photo_tools.google_photos import GooglePhotosError, HttpResponse
from photo_tools.google_photos_cli import build_parser, default_client_config, main, run

from conftest import make_folder


class UnexpectedAuthorizer:
    def authorized_transport(self, client_config_path: Path):
        raise AssertionError(f"preview attempted OAuth with {client_config_path}")


class OneAlbumTransport:
    """Minimal successful transport for a one-photo command test."""

    def __init__(self) -> None:
        self.index = 0

    def request(self, method: str, url: str, **kwargs) -> HttpResponse:
        responses = [
            HttpResponse(200, b'{"id":"album-1","productUrl":"https://photos.example/album-1"}', {}),
            HttpResponse(200, b'{"enrichmentItem":{"id":"heading-1"}}', {}),
            HttpResponse(200, b"upload-token", {}),
            HttpResponse(
                200,
                b'{"newMediaItemResults":[{"status":{"code":0},"mediaItem":{"id":"media-1","productUrl":"https://photos.example/media-1"}}]}',
                {},
            ),
        ]
        result = responses[self.index]
        self.index += 1
        return result


class FakeAuthorizer:
    def __init__(self, transport) -> None:
        self.transport = transport
        self.paths: list[Path] = []

    def authorized_transport(self, client_config_path: Path):
        self.paths.append(client_config_path)
        return self.transport


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preview_is_local_filtered_and_can_write_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])
    selected = make_folder(tmp_path, "1997-03-06-B-second", ["b.jpg"])
    before = digest(selected / "b.jpg")
    manifest = tmp_path / "manifest.md"
    args = build_parser().parse_args(
        [
            "--root",
            str(tmp_path),
            "--album-title",
            "Family scans",
            "--only",
            selected.name,
            "--manifest",
            str(manifest),
        ]
    )

    assert run(args, authorizer=UnexpectedAuthorizer()) == 0

    output = capsys.readouterr().out
    assert "1997-03-06 - B second" in output
    assert "1997-03-06 - A first" not in output
    assert "no OAuth flow or Google Photos request was performed" not in output
    assert "preview only: 1 photos in 1 folder groups" in output
    assert selected.name in manifest.read_text(encoding="utf-8")
    assert digest(selected / "b.jpg") == before


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--root", "/tmp", "--album-title", "A", "--client-config", "/tmp/client.json"],
        ["--root", "/tmp", "--album-title", "A", "--resolve-uncertain", "pending"],
        ["--root", "/tmp", "--album-title", "A", "--album-id", "manual-album"],
    ],
)
def test_invalid_or_unsupported_options_exit_without_oauth(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)
    assert raised.value.code == 2


def test_missing_default_client_configuration_exits_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])
    missing = tmp_path / "missing-client.json"
    monkeypatch.setattr(google_photos_cli, "default_client_config", lambda: missing)

    with pytest.raises(SystemExit) as raised:
        google_photos_cli.main(
            [
                "--root",
                str(tmp_path),
                "--album-title",
                "Family scans",
                "--upload",
                "--journal",
                str(tmp_path / "state.json"),
            ]
        )

    assert raised.value.code == 2
    assert "OAuth client configuration not found" in capsys.readouterr().err


def test_explicit_upload_uses_authorizer_and_writes_non_secret_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])
    before = digest(folder / "a.jpg")
    journal = tmp_path / "state.json"
    client_config = tmp_path.parent / "external-client.json"
    transport = OneAlbumTransport()
    authorizer = FakeAuthorizer(transport)
    args = build_parser().parse_args(
        [
            "--root",
            str(tmp_path),
            "--album-title",
            "Family scans",
            "--upload",
            "--client-config",
            str(client_config),
            "--journal",
            str(journal),
        ]
    )

    assert run(args, authorizer=authorizer) == 0

    output = capsys.readouterr().out
    assert authorizer.paths == [client_config]
    assert f"uploading folder: {folder.name}" in output
    assert "confirmed: 1/1 headings, 1/1 photos" in output
    assert "album ready: https://photos.example/album-1" in output
    assert "sharing remains manual" not in output
    assert "upload-token" not in output
    assert "upload-token" not in journal.read_text(encoding="utf-8")
    assert digest(folder / "a.jpg") == before


def test_explicit_upload_uses_default_client_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])
    transport = OneAlbumTransport()
    authorizer = FakeAuthorizer(transport)
    args = build_parser().parse_args(
        [
            "--root",
            str(tmp_path),
            "--album-title",
            "Family scans",
            "--upload",
            "--journal",
            str(tmp_path / "state.json"),
        ]
    )

    assert run(args, authorizer=authorizer) == 0

    capsys.readouterr()
    assert folder.is_dir()
    assert authorizer.paths == [default_client_config()]


def test_confirmed_failure_reports_each_progress_category(tmp_path: Path) -> None:
    make_folder(tmp_path, "1997-03-06-A-first", ["a.jpg"])

    class RejectedTransport:
        def request(self, method: str, url: str, **kwargs) -> HttpResponse:
            return HttpResponse(400, b'{"error":{"message":"rejected"}}', {})

    args = build_parser().parse_args(
        [
            "--root",
            str(tmp_path),
            "--album-title",
            "Family scans",
            "--upload",
            "--client-config",
            str(tmp_path.parent / "external-client.json"),
            "--journal",
            str(tmp_path / "state.json"),
        ]
    )

    with pytest.raises(GooglePhotosError) as raised:
        run(args, authorizer=FakeAuthorizer(RejectedTransport()))

    message = str(raised.value)
    assert "confirmed: 0/1 headings, 0/1 photos" in message
    assert "failed: confirmed request failure" in message
    assert "uncertain: none" in message
    assert "unattempted: 1 headings, 1 photos" in message
