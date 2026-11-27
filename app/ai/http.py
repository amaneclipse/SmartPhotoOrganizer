"""Small stdlib HTTP client: no secret or image is logged."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.ai.base import AIProviderError

class RequestLimiter:
    def __init__(self, minimum_interval: float = 0.0, max_requests: int | None = None):
        self.minimum_interval = max(0.0, minimum_interval); self.max_requests = max_requests; self.requests = 0; self.last_request = 0.0
    def acquire(self) -> None:
        if self.max_requests is not None and self.requests >= self.max_requests: raise AIProviderError("Достигнут лимит API-запросов для текущей сессии.")
        delay = self.minimum_interval - (time.monotonic() - self.last_request)
        if delay > 0: time.sleep(delay)
        self.last_request = time.monotonic(); self.requests += 1

def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            if not isinstance(result, dict): raise AIProviderError("Провайдер вернул неожиданный формат ответа.")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise AIProviderError(f"Ошибка API ({exc.code}). Проверьте ключ, модель и доступность провайдера. {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIProviderError("Не удалось подключиться к выбранному AI-провайдеру. Повторите попытку позже.") from exc
