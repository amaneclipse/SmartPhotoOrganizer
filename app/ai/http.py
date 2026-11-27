"""Small stdlib HTTP client: no secret or image is logged."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
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

@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_retries: int = 2
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0


TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
    retry_policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    """Make a JSON request without exposing response bodies or credentials.

    Only transient failures are retried. Authentication, validation and other
    permanent 4xx responses fail immediately.
    """
    policy = retry_policy or RetryPolicy()
    request_headers = {**headers, "Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    for attempt in range(policy.max_retries + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise AIProviderError("Провайдер вернул неожиданный формат ответа.")
                return result
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            if exc.code not in TRANSIENT_HTTP_CODES or attempt >= policy.max_retries:
                raise AIProviderError(f"Ошибка API ({exc.code}). Проверьте ключ, модель и доступность провайдера.") from exc
            try:
                delay = min(float(retry_after), policy.max_delay_seconds) if retry_after else policy.initial_delay_seconds * (2**attempt)
            except ValueError:
                delay = policy.initial_delay_seconds * (2**attempt)
            time.sleep(min(delay, policy.max_delay_seconds))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
            if attempt >= policy.max_retries:
                raise AIProviderError("Не удалось подключиться к выбранному AI-провайдеру. Повторите попытку позже.") from exc
            time.sleep(min(policy.initial_delay_seconds * (2**attempt), policy.max_delay_seconds))
        except json.JSONDecodeError as exc:
            raise AIProviderError("Провайдер вернул некорректный JSON-ответ.") from exc
    raise AIProviderError("Не удалось получить ответ от AI-провайдера.")


def get_json(url: str, headers: dict[str, str], timeout: float, retry_policy: RetryPolicy | None = None) -> dict[str, Any]:
    return request_json("GET", url, headers, None, timeout, retry_policy)


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float, retry_policy: RetryPolicy | None = None) -> dict[str, Any]:
    return request_json("POST", url, headers, payload, timeout, retry_policy)
