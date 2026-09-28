"""Shared test helpers."""

import base64
from pathlib import Path


JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgG"
    "BgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/wAALCAAB"
    "AAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAA"
    "AAD/2gAIAQEAAD8AVN//2Q=="
)


def make_jpeg(path: Path) -> Path:
    """Create a tiny JPEG fixture without external image libraries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(JPEG_BASE64))
    return path


def make_folder(root: Path, name: str, filenames: list[str]) -> Path:
    """Create one scan folder containing simple planning fixtures."""
    folder = root / name
    folder.mkdir(parents=True)
    for filename in filenames:
        (folder / filename).write_bytes(b"planning fixture")
    return folder
