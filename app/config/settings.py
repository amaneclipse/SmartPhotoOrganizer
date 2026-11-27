"""Non-secret user settings. API keys are deliberately excluded."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from app.ai.manager import AnalysisLimits, AnalysisMode

@dataclass(slots=True)
class AISettings:
    mode: str = AnalysisMode.LOCAL.value
    provider_id: str = "openai"
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    max_images: int = 1000
    max_requests: int = 1000
    max_budget_usd: float | None = None
    max_image_bytes: int = 4 * 1024 * 1024
    skip_processed: bool = True
    min_interval_seconds: float = 0.2
    parallel_requests: int = 20
    provider_type: str = "openai"
    def limits(self) -> AnalysisLimits: return AnalysisLimits(self.max_images, self.max_requests, self.max_budget_usd, self.max_image_bytes, self.skip_processed, self.min_interval_seconds)

def load_settings(path: Path) -> AISettings:
    if not path.exists(): return AISettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8")); allowed = {field for field in AISettings.__dataclass_fields__}; return AISettings(**{key: value for key, value in raw.items() if key in allowed})
    except (OSError, ValueError, TypeError): return AISettings()

def save_settings(path: Path, settings: AISettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
