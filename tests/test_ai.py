from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.ai.base import AIProviderError
from app.ai.http import RequestLimiter, RetryPolicy, request_json
from app.ai.manager import AIManager, AnalysisMode
from app.ai.manager import AnalysisLimits
from app.ai.compatible_provider import OpenAICompatibleProvider
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

    @patch("app.ai.http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_respects_retry_after(self, urlopen, sleep):
        import urllib.error
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        cases = (("2", 2.0, RetryPolicy(max_retries=1)), ("invalid", 0.5, RetryPolicy(max_retries=1)), ("100", 8.0, RetryPolicy(max_retries=1, max_delay_seconds=8)))
        for retry_after, expected_delay, policy in cases:
            with self.subTest(retry_after=retry_after):
                error = urllib.error.HTTPError("https://example.test", 503, "busy", {"Retry-After": retry_after}, None)
                urlopen.reset_mock(); sleep.reset_mock(); urlopen.side_effect = [error, response]
                self.assertEqual(request_json("GET", "https://example.test", {}, None, 1.0, policy), {"ok": True})
                sleep.assert_called_once_with(expected_delay)

    @patch("app.ai.http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_does_not_retry_permanent_4xx(self, urlopen, sleep):
        import urllib.error
        for status in (401, 404):
            with self.subTest(status=status):
                urlopen.reset_mock(); sleep.reset_mock()
                urlopen.side_effect = urllib.error.HTTPError("https://example.test", status, "error", {}, None)
                with self.assertRaises(AIProviderError):
                    request_json("GET", "https://example.test", {}, None, 1.0)
                sleep.assert_not_called()

    @patch("app.ai.compatible_provider.get_json")
    def test_compatible_provider_connection_uses_models_get(self, get_json):
        provider = OpenAICompatibleProvider(ProviderConfig("openai-compatible", "test-model", "https://example.test/v1", "test-key"))
        get_json.return_value = {"data": [{"id": "test-model"}]}
        self.assertIn("успешно", provider.check_connection())
        get_json.assert_called_once_with("https://example.test/v1/models", {"Authorization": "Bearer test-key"}, 60.0)
        get_json.reset_mock(); get_json.return_value = {"data": [{"id": "other-model"}]}
        with self.assertRaises(AIProviderError): provider.check_connection()

    def test_manager_enforces_max_image_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"0123456789")
            manager = AIManager(AnalysisMode.LOCAL, limits=AnalysisLimits(max_image_bytes=5))
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")

    def test_manager_handles_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image"); image.unlink()
            manager = AIManager(AnalysisMode.LOCAL)
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")

    def test_provider_wraps_read_bytes_oserror(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            provider = OpenAIProvider(ProviderConfig("openai", "test-model", "https://example.test/v1", "test-key"))
            with patch("pathlib.Path.read_bytes", side_effect=OSError("read failed")):
                with self.assertRaisesRegex(AIProviderError, "Не удалось прочитать изображение"):
                    provider.analyze_image(image, "test")
