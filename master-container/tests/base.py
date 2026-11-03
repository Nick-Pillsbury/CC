"""Shared setup for endpoint tests."""

import unittest

from fastapi.testclient import TestClient

from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.dependencies import ServiceContainer
from master_api.main import create_app
from master_api.models import SystemState
from master_api.state import SystemStateMachine


class ApiTestCase(unittest.TestCase):
    initial_system_state = SystemState.READY

    def setUp(self) -> None:
        self.hardware = MockHardwareClient()
        self.video = MockVideoClient()
        self.state_machine = SystemStateMachine(self.initial_system_state)
        self.services = ServiceContainer(
            hardware=self.hardware,
            video=self.video,
            state_machine=self.state_machine,
        )
        self.client = TestClient(create_app(self.services))

    def tearDown(self) -> None:
        self.client.close()
