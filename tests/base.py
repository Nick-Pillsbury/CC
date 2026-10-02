"""Shared setup for endpoint tests."""

import unittest

from fastapi.testclient import TestClient

from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.dependencies import ServiceContainer
from master_api.main import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.hardware = MockHardwareClient()
        self.video = MockVideoClient()
        self.client = TestClient(
            create_app(
                ServiceContainer(hardware=self.hardware, video=self.video)
            )
        )

    def tearDown(self) -> None:
        self.client.close()
