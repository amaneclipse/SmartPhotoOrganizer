"""Recursive image discovery with resumable-friendly records."""
from collections.abc import Callable, Iterator
from pathlib import Path
from app.metadata.extractor import extract_metadata
from app.models import ImageRecord
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".gif", ".avif", ".dng", ".cr2", ".nef", ".arw"}

def scan_images(roots: list[Path], should_stop: Callable[[], bool] | None = None) -> Iterator[ImageRecord]:
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir(): continue
        for path in root.rglob("*"):
            if should_stop and should_stop(): return
            try:
                resolved = path.resolve()
                if resolved in seen or not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS: continue
                seen.add(resolved); stat = path.stat(); metadata = extract_metadata(path)
                yield ImageRecord(path, stat.st_size, stat.st_mtime, int(metadata.get("width", 0)), int(metadata.get("height", 0)), str(metadata.get("format", path.suffix.upper().lstrip("."))), metadata=metadata)
            except (OSError, PermissionError): continue
