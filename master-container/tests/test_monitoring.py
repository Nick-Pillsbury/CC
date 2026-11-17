"""Verify durable history, fault detection, stale data, and spectator updates."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from master_api.clients.errors import DownstreamUnavailableError
from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.config import Settings
from master_api.dependencies import ServiceContainer
from master_api.journal import Journal
from master_api.lease import ControlLeaseError
from master_api.main import create_app
from master_api.models import SystemState
from tests.base import ApiTestCase


class JournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_persists_and_retention_is_per_kind(self):
        with TemporaryDirectory() as folder:
            path = str(Path(folder) / "history.sqlite3")
            journal = Journal(path, limit=2)
            for index in range(4):
                await journal.record("test", index=index)
            await journal.append("telemetry", {"throttle": 0.2})
            await journal.close()
            reopened = Journal(path, limit=2)
            try:
                events = await reopened.read("event")
                self.assertEqual([2, 3], [item["data"]["index"] for item in events])
                self.assertEqual(1, len(await reopened.read("telemetry")))
                self.assertEqual([events[1]], await reopened.read("event", after=events[0]["id"]))
            finally:
                await reopened.close()

    async def test_write_failure_is_reported_without_blocking_safety(self):
        journal = Journal()
        await journal.close()
        with self.assertLogs("master_api.journal", level="ERROR"):
            await journal.record("after_close")
        self.assertEqual("history_write_failed", journal.last_error)


class MonitoringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hardware = MockHardwareClient()
        self.video = MockVideoClient()
        self.services = ServiceContainer(self.hardware, self.video, monitor_interval_seconds=0.02)
        await self.services.check_readiness()

    async def asyncTearDown(self):
        await self.services.stop_monitoring()
        await self.services.lease_manager.shutdown()
        await self.services.journal.close()

    async def test_background_failure_revokes_driver_without_health_request(self):
        lease = await self.services.lease_manager.acquire("driver")
        self.hardware.throttle = 0.7
        await self.services.start_monitoring()
        self.video.ready = False
        for _ in range(100):
            if self.services.state_machine.snapshot().system_state == SystemState.EMERGENCY_STOP:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(SystemState.EMERGENCY_STOP, self.services.state_machine.snapshot().system_state)
        self.assertEqual(0, self.hardware.throttle)
        with self.assertRaises(ControlLeaseError):
            await self.services.lease_manager.authorize(lease.lease_id)
        events = await self.services.journal.read("event")
        self.assertTrue(any(item["data"].get("current") == "EMERGENCY_STOP" for item in events))

    async def test_failed_sample_keeps_previous_value_and_timestamp_marked_stale(self):
        self.hardware.throttle = 0.4
        original = await self.services.collect_telemetry()
        self.hardware.telemetry = AsyncMock(side_effect=DownstreamUnavailableError("hardware", "offline"))
        failed = await self.services.collect_telemetry()
        self.assertEqual(0.4, failed.hardware.throttle)
        self.assertEqual(original.observed_at["hardware"], failed.observed_at["hardware"])
        self.assertEqual(["hardware"], failed.stale_components)
        self.assertEqual("downstream_unavailable", failed.errors["hardware"])
        self.hardware.telemetry = AsyncMock(return_value=original.hardware)
        recovered = await self.services.collect_telemetry()
        self.assertEqual([], recovered.stale_components)

    async def test_no_previous_sample_is_null_when_hardware_unavailable(self):
        self.hardware.telemetry = AsyncMock(side_effect=DownstreamUnavailableError("hardware", "offline"))
        sample = await self.services.collect_telemetry()
        self.assertIsNone(sample.hardware)
        self.assertIn("hardware", sample.stale_components)

    async def test_slow_spectator_receives_latest_sample_and_unsubscribes(self):
        async with self.services.subscribe_telemetry() as queue:
            for throttle in (0.1, 0.3, 0.8):
                self.hardware.throttle = throttle
                await self.services.collect_telemetry()
            self.assertEqual(1, queue.qsize())
            self.assertEqual(0.8, queue.get_nowait().hardware.throttle)
        self.assertEqual(0, len(self.services._subscribers))


class HistoryEndpointTests(ApiTestCase):
    def test_events_do_not_leak_lease_or_headers_or_client_input(self):
        response = self.client.post("/api/v1/control/lease", json={"client_id": "secret-client-name"},
                                    headers={"Authorization": "Bearer secret-auth", "X-Request-ID": "secret-id"})
        lease = response.json()["lease_id"]
        self.client.post("/api/v1/control/lease/heartbeat", headers={"X-Control-Lease": lease})
        self.client.get("/unknown-secret?token=secret-query")
        text = self.client.get("/api/v1/system/events").text
        for secret in (lease, "secret-client-name", "secret-auth", "secret-id", "unknown-secret", "secret-query"):
            self.assertNotIn(secret, text)
        self.assertIn("state_transition", text)
        self.assertIn(response.headers["x-request-id"], text)

    def test_history_contains_samples_and_validates_page_bounds(self):
        self.client.get("/api/v1/telemetry")
        history = self.client.get("/api/v1/telemetry/history").json()
        self.assertEqual(1, len(history["items"]))
        self.assertEqual(0, history["items"][0]["data"]["hardware"]["throttle"])
        self.assertEqual(422, self.client.get("/api/v1/telemetry/history?limit=1001").status_code)

    def test_two_websocket_spectators_receive_snapshots(self):
        with self.client.websocket_connect("/api/v1/telemetry/ws") as first:
            with self.client.websocket_connect("/api/v1/telemetry/ws") as second:
                self.assertEqual(0, first.receive_json()["hardware"]["throttle"])
                self.assertEqual(0, second.receive_json()["hardware"]["throttle"])
        self.assertEqual(0, len(self.services._subscribers))


class RuntimeMonitoringTests(unittest.TestCase):
    def test_runtime_starts_and_stops_monitoring(self):
        app = create_app(settings=Settings(client_mode="mock"))
        with TestClient(app) as client:
            services = app.state.services
            self.assertTrue(client.get("/api/v1/system/monitoring").json()["running"])
        self.assertEqual([], services._tasks)
        self.assertIsNone(services.lease_manager._watchdog_task)
