"""Adapter boundary for future local ONNX/CLIP/OCR implementations."""
from pathlib import Path
from app.ai.base import AIProvider, AIProviderError, AnalysisResponse, ProviderConfig

class LocalProvider(AIProvider):
    provider_id, display_name, cloud = "local", "Локальная модель", False
    def check_connection(self) -> str: return "Локальный baseline доступен без API-ключа."
    def analyze_image(self, image_path: Path, prompt: str) -> AnalysisResponse:
        raise AIProviderError("Для детального локального AI-анализа ещё не установлена модель. Доступен базовый локальный классификатор.")
