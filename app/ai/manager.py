"""Mode selection, budgets, retries and provider construction."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from app.ai.base import AIProvider, AIProviderError, ProviderConfig
from app.ai.compatible_provider import OpenAICompatibleProvider
from app.ai.local_provider import LocalProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.http import RequestLimiter

class AnalysisMode(StrEnum): LOCAL = "local"; CLOUD = "cloud"; HYBRID = "hybrid"
@dataclass(slots=True)
class AnalysisLimits:
    max_images: int = 1000
    max_requests: int = 1000
    max_budget_usd: float | None = None
    max_image_bytes: int = 4 * 1024 * 1024
    skip_processed: bool = True
    min_interval_seconds: float = 0.2

class AIManager:
    def __init__(self, mode: AnalysisMode, config: ProviderConfig | None = None, limits: AnalysisLimits | None = None):
        self.mode, self.limits, self.requests, self.images_analyzed, self.spent_usd = mode, limits or AnalysisLimits(), 0, 0, 0.0
        self.provider: AIProvider = LocalProvider(ProviderConfig("local", "baseline", ""))
        if mode != AnalysisMode.LOCAL:
            if config is None: raise AIProviderError("Для облачного режима не настроен провайдер.")
            limiter = RequestLimiter(self.limits.min_interval_seconds, self.limits.max_requests)
            self.provider = OpenAIProvider(config, limiter) if config.provider_id == "openai" else OpenAICompatibleProvider(config, limiter)
    def check_connection(self) -> str: return self.provider.check_connection()
    def analyze(self, image_path: Path, prompt: str) -> dict:
        if self.images_analyzed >= self.limits.max_images: raise AIProviderError("Достигнут лимит изображений для текущей сессии.")
        if self.requests >= self.limits.max_requests: raise AIProviderError("Достигнут лимит запросов.")
        if self.limits.max_budget_usd is not None and self.spent_usd >= self.limits.max_budget_usd:
            raise AIProviderError("Достигнут лимит бюджета.")
        try:
            image_size = image_path.stat().st_size
        except OSError as exc:
            raise AIProviderError(f"Не удалось прочитать изображение: {image_path.name}") from exc
        if image_size > self.limits.max_image_bytes: raise AIProviderError("Изображение превышает установленный лимит размера.")
        response = self.provider.analyze_image(image_path, prompt)
        self.requests += response.request_count; self.images_analyzed += 1
        if response.estimated_cost_usd is not None:
            self.spent_usd += response.estimated_cost_usd
            if self.limits.max_budget_usd is not None and self.spent_usd >= self.limits.max_budget_usd:
                raise AIProviderError("Достигнут лимит бюджета.")
        return response.data
