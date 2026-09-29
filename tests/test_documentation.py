"""Documentation contract tests."""

from pathlib import Path


README = Path(__file__).parents[1] / "README.md"
GOOGLE_ACCEPTANCE = Path(__file__).parents[1] / "docs" / "google-photos-acceptance.md"


def test_readme_is_a_compact_operational_runbook() -> None:
    text = README.read_text(encoding="utf-8")

    assert len(text.splitlines()) < 150
    assert "uv sync" in text
    assert "YYYY-MM-DD-description" in text
    assert "uv run scan-metadata" in text
    assert "--apply" in text
    assert "--backup" in text
    assert "ImageDataHash" in text


def test_readme_documents_primary_google_workflow_and_recovery() -> None:
    text = README.read_text(encoding="utf-8")

    assert "google-photos-upload" in text
    assert "--album-title" in text
    assert "--client-config" in text
    assert "~/.config/photo-tools/google-photos-client.json" in text
    assert "override the default OAuth file" in text
    assert "--upload" in text
    assert "--only" in text
    assert "--resolve-uncertain" in text
    assert "operating-system credential store" in text
    assert "Original quality" in text
    assert "20,000" in text
    assert "app-owned album" in text
    assert "complete-plan chronological positions" in text
    assert "application-created photo still appears in journaled order" in text
    assert "cannot validate manually moved headings" in text
    assert "unrelated photos" in text
    assert "configure recipients, link sharing, collaboration, comments, and likes manually" in text


def test_google_acceptance_record_excludes_secret_values() -> None:
    text = GOOGLE_ACCEPTANCE.read_text(encoding="utf-8")

    assert "native description" in text
    assert "Second account" in text
    assert "Source SHA-256 hashes unchanged" in text
    assert "Chronological Incremental Insertion" in text
    assert "early, middle, late heading order visually confirmed" in text
    assert "early, middle, late photograph order visually confirmed" in text
    assert "Do not record client secrets" in text
