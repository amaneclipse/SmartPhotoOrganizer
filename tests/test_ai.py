from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.ai.base import AIProviderError
from app.ai.http import RequestLimiter, RetryPolicy, request_json
from app.ai.manager import AIManager, AnalysisMode
from app.ai.openai_provider import OpenAIProvider
from app.ai.base import AnalysisResponse, ProviderConfig
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

    def test_manager_enforces_image_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            manager = AIManager(AnalysisMode.LOCAL)
            manager.limits.max_images = 0
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")

    @patch("app.ai.openai_provider.get_json")
    def test_openai_connection_uses_models_get(self, get_json):
        get_json.return_value = {"data": [{"id": "test-model"}]}
        provider = OpenAIProvider(ProviderConfig("openai", "test-model", "https://example.test/v1", "test-key"))
        self.assertIn("успешно", provider.check_connection())
        get_json.assert_called_once_with("https://example.test/v1/models", {"Authorization": "Bearer test-key"}, 60.0)

    @patch("app.ai.http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_retries_transient_error(self, urlopen, sleep):
        import urllib.error
        error = urllib.error.HTTPError("https://example.test", 503, "busy", {}, None)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        urlopen.side_effect = [error, response]
        result = request_json("GET", "https://example.test", {}, None, 1.0, RetryPolicy(max_retries=1, initial_delay_seconds=0))
        self.assertTrue(result["ok"]); sleep.assert_called_once()
