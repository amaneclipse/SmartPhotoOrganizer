"""Stable interface implemented by cloud and local AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(slots=True)
class ProviderConfig:
    provider_id: str
    model: str
    base_url: str
    api_key: str = field(repr=False, default="")
    timeout_seconds: float = 60.0

@dataclass(slots=True)
class AnalysisResponse:
    data: dict[str, Any]
    request_count: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None

class AIProviderError(RuntimeError):
    """A user-facing provider failure, safe to show without leaking secrets."""

class AIProvider(ABC):
    provider_id: str
    display_name: str
    cloud: bool = True

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def check_connection(self) -> str:
        """Validate credentials and model availability."""

    @abstractmethod
    def analyze_image(self, image_path: Path, prompt: str) -> AnalysisResponse:
        """Analyze one image and return validated JSON-like data."""

    def estimate_cost(self, image_count: int) -> float | None:
        return None
