"""Shared domain models."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(slots=True)
class ImageRecord:
    path: Path
    size: int
    modified_at: float
    width: int = 0
    height: int = 0
    format: str = ""
    sha256: str | None = None
    phash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ClassificationResult:
    category: str
    subcategory: str
    source: str
    confidence: float
    tags: list[str] = field(default_factory=list)
    is_screenshot: bool = False
    screenshot_kind: str = ""
    text: str = ""
    orientation: str = ""
    reason: str = ""

@dataclass(slots=True)
class SortPlanItem:
    source: Path
    destination: Path
    result: ClassificationResult
    action: str = "copy"
    status: str = "planned"
    error: str = ""
