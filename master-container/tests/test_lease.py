"""Concurrency and timeout tests for exclusive driving control."""

import asyncio
import unittest

from master_api.clients.mock import MockHardwareClient
from master_api.lease import ControlLeaseError, ControlLeaseManager
from master_api.models import MotionCommand, SystemState
from master_api.state import SystemStateMachine


class ControlLeaseManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hardware = MockHardwareClient()
        self.state_machine = SystemStateMachine(SystemState.READY)
        self.manager = ControlLeaseManager(
            self.hardware,
            self.state_machine,
            duration_seconds=0.05,
        )
        await self.manager.start()

    async def asyncTearDown(self) -> None:
        await self.manager.shutdown()

    async def test_concurrent_acquisition_has_exactly_one_winner(self) -> None:
        results = await asyncio.gather(
            self.manager.acquire("driver-a"),
            self.manager.acquire("driver-b"),
            return_exceptions=True,
        )

        winners = [result for result in results if not isinstance(result, Exception)]
        conflicts = [result for result in results if isinstance(result, ControlLeaseError)]
        self.assertEqual(1, len(winners))
        self.assertEqual(1, len(conflicts))

    async def test_expired_lease_neutralizes_motion(self) -> None:
        lease = await self.manager.acquire("driver-a")
        command = MotionCommand.model_validate(
            {
                "steering": 0.4,
                "throttle": 0.7,
                "sequence": 1,
                "client_sent_at": "2026-10-09T11:59:59Z",
            }
        )
        await self.manager.apply_motion(lease.lease_id, command)

        await asyncio.sleep(0.12)

        self.assertEqual(0.0, self.hardware.steering)
        self.assertEqual(0.0, self.hardware.throttle)
        self.assertEqual(SystemState.READY, self.state_machine.snapshot().system_state)
