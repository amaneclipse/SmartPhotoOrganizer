from pathlib import Path
import tempfile
import unittest

from app.ai.base import AIProviderError
from app.ai.http import RequestLimiter
from app.ai.manager import AIManager, AnalysisMode
from app.config.settings import AISettings, load_settings, save_settings


class TestAI(unittest.TestCase):
    def test_local_manager_requires_no_key(self):
        manager = AIManager(AnalysisMode.LOCAL)
        self.assertIn("локальный", manager.check_connection().lower())

    def test_request_limiter_enforces_count(self):
        limiter = RequestLimiter(max_requests=1); limiter.acquire()
        with self.assertRaises(AIProviderError): limiter.acquire()

    def test_settings_do_not_contain_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            save_settings(settings_path, AISettings(model="test-model"))
            loaded = load_settings(settings_path)
            self.assertEqual(loaded.model, "test-model")
            self.assertNotIn("api_key", settings_path.read_text(encoding="utf-8"))
