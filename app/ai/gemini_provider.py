"""Native Google Gemini API provider."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import quote

from app.ai.base import AIProvider, AIProviderError, AnalysisResponse, ProviderConfig
from app.ai.http import RequestLimiter, get_json, post_json, prepare_image_for_ai
from app.ai.pricing import estimate_cost_usd


class GeminiProvider(AIProvider):
    provider_id, display_name = "gemini", "Google Gemini"

    def __init__(self, config: ProviderConfig, limiter: RequestLimiter | None = None):
        super().__init__(config)
        self.limiter = limiter or RequestLimiter(0.2)

    def _model_name(self) -> str:
        model = self.config.model.strip()
        return model.rsplit("/", 1)[-1]

    def _url(self, suffix: str = "") -> str:
        """Build the native Gemini Developer API v1beta URL.

        The native API is global by hostname and does not use a
        ``locations/global`` path. That path belongs to Vertex AI, which
        requires a project and OAuth credentials rather than an API key.
        """
        model = quote(self._model_name(), safe="")
        root = "https://generativelanguage.googleapis.com/v1beta"
        return f"{root}/models/{model}:generateContent?key={self.config.api_key}" if suffix == "/generateContent" else f"{root}/models{suffix}?key={self.config.api_key}"

    def _available_models(self) -> list[str]:
        try:
            result = get_json(self._url(""), {}, self.config.timeout_seconds)
            return [str(item["name"]).rsplit("/", 1)[-1] for item in result.get("models", []) if isinstance(item, dict) and item.get("name")]
        except (AIProviderError, OSError, ValueError, TypeError):
            return []

    def _model_error(self) -> AIProviderError:
        models = self._available_models()
        available = ", ".join(models) if models else "список недоступен"
        return AIProviderError(f"Модель {self._model_name()} не найдена в Google Gemini. Доступные модели: {available}.")

    def check_connection(self) -> str:
        if not self.config.api_key:
            raise AIProviderError("API-ключ не введён.")
        result = get_json(self._url(""), {}, self.config.timeout_seconds)
        models = {str(item.get("name", "")).rsplit("/", 1)[-1] for item in result.get("models", []) if isinstance(item, dict)}
        if models and self._model_name() not in models:
            raise self._model_error()
        return f"Подключение успешно. Модель: {self._model_name()}"

    def analyze_image(self, image_path: Path, prompt: str) -> AnalysisResponse:
        self.limiter.acquire()
        try:
            encoded = base64.b64encode(prepare_image_for_ai(image_path)).decode("ascii")
        except (OSError, ValueError) as exc:
            raise AIProviderError(f"Не удалось прочитать изображение: {image_path.name}") from exc
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": encoded}}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            result = post_json(self._url("/generateContent"), {}, payload, self.config.timeout_seconds)
        except AIProviderError as exc:
            if "(404)" in str(exc): raise self._model_error() from exc
            raise
        try:
            output_text = result["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(output_text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError("Google Gemini вернул некорректный структурированный результат.") from exc
        usage = result.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount")
        output_tokens = usage.get("candidatesTokenCount")
        return AnalysisResponse(data, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=estimate_cost_usd(self.config.model, input_tokens, output_tokens))
