"""Tests for application-scoped downstream client resources."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from master_api.clients.http import HttpHardwareClient, HttpVideoClient
from master_api.config import Settings
from master_api.main import create_app


class LifespanTests(unittest.TestCase):
    def test_http_client_is_shared_and_closed_with_application(self) -> None:
        instances: list[FakeAsyncClient] = []

        class FakeAsyncClient:
            def __init__(self, **kwargs: object) -> None:
                self.kwargs = kwargs
                self.entered = False
                self.closed = False
                instances.append(self)

            async def __aenter__(self) -> "FakeAsyncClient":
                self.entered = True
                return self

            async def __aexit__(self, *args: object) -> None:
                self.closed = True

        settings = Settings(
            client_mode="http",
            hardware_base_url="http://hardware.test",
            video_base_url="http://video.test",
        )

        with patch("master_api.main.httpx.AsyncClient", FakeAsyncClient):
            app = create_app(settings=settings)
            with TestClient(app):
                shared_client = instances[0]
                self.assertTrue(shared_client.entered)
                self.assertIsInstance(app.state.services.hardware, HttpHardwareClient)
                self.assertIsInstance(app.state.services.video, HttpVideoClient)
                self.assertIs(
                    shared_client,
                    app.state.services.hardware._http_client,
                )
                self.assertIs(
                    shared_client,
                    app.state.services.video._http_client,
                )
                self.assertFalse(shared_client.closed)

        self.assertTrue(shared_client.closed)
