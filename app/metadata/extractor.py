"""Metadata and screenshot heuristics; no network calls are made."""
import re
from pathlib import Path
from typing import Any
try:
    from PIL import ExifTags, Image
except ImportError:  # optional dependency
    Image = ExifTags = None

def extract_metadata(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if Image is None: return data
    try:
        with Image.open(path) as image:
            data.update(width=image.width, height=image.height, format=image.format or path.suffix.upper().lstrip("."))
            exif = image.getexif()
            if exif and ExifTags:
                named = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
                for key in ("Make", "Model", "DateTimeOriginal", "Software", "Orientation"):
                    if key in named: data[key] = str(named[key])
    except (OSError, ValueError): pass
    return data

def detect_screenshot(path: Path, metadata: dict[str, Any]) -> tuple[bool, str, float]:
    width, height = int(metadata.get("width", 0)), int(metadata.get("height", 0)); name = path.name.lower(); software = str(metadata.get("Software", "")).lower(); score = 0.0
    if re.search(r"screenshot|screen.?shot|скрин|снимок экрана", name): score += 0.75
    if software and any(token in software for token in ("snipping", "screenshot", "android", "ios")): score += 0.65
    if width and height and ((width >= 1000 and height >= 600 and width / height > 1.45) or width in {1080, 1170, 1440, 1920, 2560, 3840}): score += 0.20
    if not metadata.get("Make") and not metadata.get("Model") and width and height and width / height > 1.5: score += 0.10
    if score < 0.65: return False, "", score
    kind = "Windows" if "snipping" in software or "windows" in name else "Android/iPhone" if "android" in software or "iphone" in name else "Неопределённые"
    return True, kind, min(score, 0.99)
