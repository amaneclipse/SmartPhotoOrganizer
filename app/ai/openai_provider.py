"""OpenAI Responses API provider with direct user-to-provider requests."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from app.ai.base import AIProvider, AIProviderError, AnalysisResponse, ProviderConfig
from app.ai.http import RequestLimiter, get_json, post_json
from app.ai.prompt import CLASSIFICATION_SCHEMA

class OpenAIProvider(AIProvider):
    provider_id, display_name = "openai", "OpenAI"
    def __init__(self, config: ProviderConfig, limiter: RequestLimiter | None = None):
        super().__init__(config); self.limiter = limiter or RequestLimiter(0.2)
    def _url(self, suffix: str) -> str: return self.config.base_url.rstrip("/") + suffix
    def check_connection(self) -> str:
        if not self.config.api_key: raise AIProviderError("API-ключ не введён.")
        result = get_json(self._url("/models"), {"Authorization": f"Bearer {self.config.api_key}"}, self.config.timeout_seconds)
        models = {str(item.get("id")) for item in result.get("data", []) if isinstance(item, dict)}
        if self.config.model not in models and models: raise AIProviderError(f"Модель {self.config.model} недоступна для этого ключа.")
        return f"Подключение успешно. Модель: {self.config.model}"
    def analyze_image(self, image_path: Path, prompt: str) -> AnalysisResponse:
        self.limiter.acquire()
        try:
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise AIProviderError(f"Не удалось прочитать изображение: {image_path.name}") from exc
        mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        payload = {"model": self.config.model, "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}]}], "text": {"format": {"type": "json_schema", "name": "photo_classification", "strict": True, "schema": CLASSIFICATION_SCHEMA}}}
        result = post_json(self._url("/responses"), {"Authorization": f"Bearer {self.config.api_key}"}, payload, self.config.timeout_seconds)
        output_text = result.get("output_text") or ""
        if not output_text:
            for item in result.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}: output_text = content.get("text", ""); break
        try: data = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc: raise AIProviderError("Провайдер вернул некорректный структурированный результат.") from exc
        usage = result.get("usage", {}); return AnalysisResponse(data, input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))
