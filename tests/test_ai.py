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
from app.ai.pricing import estimate_cost_usd
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

    def test_pricing_known_and_unknown_models(self):
        self.assertEqual(estimate_cost_usd("gpt-4.1-mini", 1_000_000, 1_000_000), 2.0)
        self.assertIsNone(estimate_cost_usd("unknown-model", 1_000_000, 1_000_000))
        self.assertIsNone(estimate_cost_usd("gpt-4.1-mini", None, None))

    @patch("app.ai.openai_provider.post_json")
    def test_openai_provider_populates_estimated_cost(self, post_json):
        post_json.return_value = {"output_text": '{"category": "Разное"}', "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            provider = OpenAIProvider(ProviderConfig("openai", "gpt-4.1-mini", "https://example.test/v1", "test-key"))
            response = provider.analyze_image(image, "test")
        self.assertEqual(response.estimated_cost_usd, 2.0)

    @patch("app.ai.compatible_provider.post_json")
    def test_compatible_provider_populates_estimated_cost(self, post_json):
        post_json.return_value = {"choices": [{"message": {"content": '{"category": "Разное"}'}}], "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            provider = OpenAICompatibleProvider(ProviderConfig("openai-compatible", "gpt-4.1-mini", "https://example.test/v1", "test-key"))
            response = provider.analyze_image(image, "test")
        self.assertEqual(response.estimated_cost_usd, 2.0)

    def test_manager_accumulates_cost_and_blocks_after_exceeding_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            manager = AIManager(AnalysisMode.LOCAL, limits=AnalysisLimits(max_budget_usd=0.01))
            manager.provider = MagicMock()
            manager.provider.analyze_image.return_value = AnalysisResponse({}, estimated_cost_usd=0.02)
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")
            self.assertEqual(manager.spent_usd, 0.02)
            manager.provider.analyze_image.reset_mock()
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")
            manager.provider.analyze_image.assert_not_called()

    def test_budget_exact_limit_does_not_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            manager = AIManager(AnalysisMode.LOCAL, limits=AnalysisLimits(max_budget_usd=0.01))
            manager.provider = MagicMock()
            manager.provider.analyze_image.return_value = AnalysisResponse({}, request_count=1, estimated_cost_usd=0.01)
            manager.analyze(image, "test")
            self.assertEqual(manager.spent_usd, 0.01)
            with self.assertRaises(AIProviderError): manager.analyze(image, "test")
            manager.provider.analyze_image.assert_called_once()

    def test_budget_none_means_unlimited(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            manager = AIManager(AnalysisMode.LOCAL, limits=AnalysisLimits(max_budget_usd=None))
            manager.provider = MagicMock()
            manager.provider.analyze_image.return_value = AnalysisResponse({}, request_count=1, estimated_cost_usd=999.0)
            manager.analyze(image, "test")
            self.assertEqual(manager.spent_usd, 999.0)

    def test_budget_ignores_unknown_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            manager = AIManager(AnalysisMode.LOCAL, limits=AnalysisLimits(max_budget_usd=0.001))
            manager.provider = MagicMock()
            manager.provider.analyze_image.return_value = AnalysisResponse({}, request_count=1, estimated_cost_usd=None)
            manager.analyze(image, "test")
            self.assertEqual(manager.spent_usd, 0.0)

    def test_estimate_cost_usd_known_model(self):
        self.assertEqual(estimate_cost_usd("gpt-4o", 1000, 500), (1000 * 2.5 + 500 * 10) / 1_000_000)

    def test_estimate_cost_usd_unknown_model(self):
        self.assertIsNone(estimate_cost_usd("unknown-model", 1000, 500))

    @patch("app.ai.openai_provider.post_json")
    def test_openai_provider_fills_estimated_cost(self, post_json):
        post_json.return_value = {"choices": [{"message": {"content": '{"category": "test"}'}}], "output_text": '{"category": "test"}', "usage": {"input_tokens": 1000, "output_tokens": 500}}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"; image.write_bytes(b"image")
            provider = OpenAIProvider(ProviderConfig("openai", "gpt-4o", "https://example.test/v1", "test-key"))
            response = provider.analyze_image(image, "prompt")
        self.assertEqual(response.input_tokens, 1000)
        self.assertEqual(response.output_tokens, 500)
        self.assertEqual(response.estimated_cost_usd, (1000 * 2.5 + 500 * 10) / 1_000_000)
