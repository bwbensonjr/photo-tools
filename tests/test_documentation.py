"""Documentation contract tests."""

from pathlib import Path


README = Path(__file__).parents[1] / "README.md"
GOOGLE_ACCEPTANCE = Path(__file__).parents[1] / "docs" / "google-photos-acceptance.md"


def test_readme_documents_apple_workflows_and_sources() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Shared Albums do not" in text
    assert "separate manual entry" in text
    assert "iCloud Shared Photo Library" in text
    assert "https://support.apple.com/guide/photos/phta4e5a733f/mac" in text
    assert "https://support.apple.com/guide/photos/pht5f6df5f0/mac" in text
    assert "https://support.apple.com/guide/photos/pht153ab3a01/mac" in text
    assert "Post to Shared Album" not in text
    assert "Shortcut" not in text


def test_readme_documents_primary_google_workflow_and_recovery() -> None:
    text = README.read_text(encoding="utf-8")

    assert "google-photos-upload" in text
    assert "--album-title" in text
    assert "--client-config" in text
    assert "--upload" in text
    assert "--only" in text
    assert "--resolve-uncertain" in text
    assert "operating-system credential store" in text
    assert "Original quality" in text
    assert "20,000" in text
    assert "app-created" in text
    assert "Share once after upload" in text
    assert "not an agent skill" in text


def test_google_acceptance_record_excludes_secret_values() -> None:
    text = GOOGLE_ACCEPTANCE.read_text(encoding="utf-8")

    assert "native description" in text
    assert "Second account" in text
    assert "Source SHA-256 hashes unchanged" in text
    assert "Do not record client secrets" in text


def test_readme_documents_safety_and_migration() -> None:
    text = README.read_text(encoding="utf-8")

    assert "dry run" in text
    assert "--backup" in text
    assert "ImageDataHash" in text
    assert "Scans/.scan-tools/tag_scans.py" in text
    assert "does not delete" in text
