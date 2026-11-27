"""OpenAI-compatible chat-completions provider for other hosted services."""
from __future__ import annotations
import base64, json, mimetypes
from pathlib import Path
from app.ai.base import AIProvider, AIProviderError, AnalysisResponse, ProviderConfig
from app.ai.http import RequestLimiter, post_json

class OpenAICompatibleProvider(AIProvider):
    provider_id, display_name = "openai-compatible", "OpenAI-compatible API"
    def __init__(self, config: ProviderConfig, limiter: RequestLimiter | None = None): super().__init__(config); self.limiter = limiter or RequestLimiter(0.2)
    def check_connection(self) -> str:
        if not self.config.api_key: raise AIProviderError("API-ключ не введён.")
        post_json(self.config.base_url.rstrip("/") + "/models", {"Authorization": f"Bearer {self.config.api_key}"}, {}, self.config.timeout_seconds); return f"Подключение успешно. Модель: {self.config.model}"
    def analyze_image(self, image_path: Path, prompt: str) -> AnalysisResponse:
        self.limiter.acquire(); encoded = base64.b64encode(image_path.read_bytes()).decode("ascii"); mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        payload = {"model": self.config.model, "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}]}], "response_format": {"type": "json_object"}}
        result = post_json(self.config.base_url.rstrip("/") + "/chat/completions", {"Authorization": f"Bearer {self.config.api_key}"}, payload, self.config.timeout_seconds)
        try: data = json.loads(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc: raise AIProviderError("OpenAI-compatible провайдер вернул некорректный ответ.") from exc
        usage = result.get("usage", {}); return AnalysisResponse(data, input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))
