"""Tests for environment-backed downstream configuration."""

import unittest

from master_api.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_http_mode_and_timeouts_are_loaded_from_environment(self) -> None:
        settings = Settings.from_env(
            {
                "MASTER_API_CLIENT_MODE": "HTTP",
                "MASTER_API_HARDWARE_BASE_URL": "http://hardware.test:8100/",
                "MASTER_API_VIDEO_BASE_URL": "https://video.test/api/",
                "MASTER_API_HTTP_CONNECT_TIMEOUT_SECONDS": "0.1",
                "MASTER_API_HTTP_READ_TIMEOUT_SECONDS": "0.2",
                "MASTER_API_HTTP_WRITE_TIMEOUT_SECONDS": "0.3",
                "MASTER_API_HTTP_POOL_TIMEOUT_SECONDS": "0.4",
            }
        )

        self.assertEqual("http", settings.client_mode)
        self.assertEqual("http://hardware.test:8100", settings.hardware_base_url)
        self.assertEqual("https://video.test/api", settings.video_base_url)
        timeout = settings.http_timeout()
        self.assertEqual(0.1, timeout.connect)
        self.assertEqual(0.2, timeout.read)
        self.assertEqual(0.3, timeout.write)
        self.assertEqual(0.4, timeout.pool)

    def test_mock_mode_is_the_safe_default(self) -> None:
        settings = Settings.from_env({})

        self.assertEqual("mock", settings.client_mode)

    def test_unknown_client_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "must be either"):
            Settings.from_env({"MASTER_API_CLIENT_MODE": "direct-gpio"})

    def test_non_positive_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "greater than zero"):
            Settings.from_env(
                {"MASTER_API_HTTP_READ_TIMEOUT_SECONDS": "0"}
            )

    def test_non_http_service_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "absolute HTTP"):
            Settings.from_env(
                {"MASTER_API_HARDWARE_BASE_URL": "hardware.internal:8000"}
            )
