"""Unit tests for guarded system-state transitions."""

import asyncio
import unittest

from master_api.models import SystemState
from master_api.state import StateConflictError, SystemStateMachine


class SystemStateMachineTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_controlled_and_release_transitions(self) -> None:
        machine = SystemStateMachine()

        ready = await machine.reconcile_health(
            hardware_ready=True,
            video_ready=True,
        )
        controlled = await machine.transition(
            SystemState.CONTROLLED,
            "Driver acquired control",
        )
        released = await machine.transition(
            SystemState.READY,
            "Driver released control",
        )

        self.assertEqual(SystemState.READY, ready.system_state)
        self.assertEqual(SystemState.CONTROLLED, controlled.system_state)
        self.assertEqual(SystemState.READY, released.system_state)

    async def test_hardware_failure_while_controlled_enters_emergency_stop(self) -> None:
        machine = SystemStateMachine(SystemState.CONTROLLED)

        state = await machine.reconcile_health(
            hardware_ready=False,
            video_ready=True,
        )

        self.assertEqual(SystemState.EMERGENCY_STOP, state.system_state)
        self.assertEqual("Hardware is unavailable", state.reason)

    async def test_emergency_stop_is_not_cleared_by_healthy_dependencies(self) -> None:
        machine = SystemStateMachine(SystemState.EMERGENCY_STOP)

        state = await machine.reconcile_health(
            hardware_ready=True,
            video_ready=True,
        )

        self.assertEqual(SystemState.EMERGENCY_STOP, state.system_state)

    async def test_illegal_transition_preserves_state(self) -> None:
        machine = SystemStateMachine(SystemState.DEGRADED)

        with self.assertRaises(StateConflictError):
            await machine.transition(
                SystemState.CONTROLLED,
                "Illegal control acquisition",
            )

        self.assertEqual(SystemState.DEGRADED, machine.snapshot().system_state)

    async def test_concurrent_transitions_are_serialized(self) -> None:
        machine = SystemStateMachine(SystemState.READY)

        results = await asyncio.gather(
            machine.transition(SystemState.CONTROLLED, "Driver acquired control"),
            machine.transition(SystemState.DEGRADED, "Video service failed"),
        )

        self.assertEqual(SystemState.DEGRADED, results[-1].system_state)
        self.assertEqual(SystemState.DEGRADED, machine.snapshot().system_state)

    async def test_shutdown_is_terminal(self) -> None:
        machine = SystemStateMachine(SystemState.READY)
        await machine.transition(SystemState.SHUTTING_DOWN, "Shutdown")

        with self.assertRaises(StateConflictError):
            await machine.transition(SystemState.READY, "Restart")

    async def test_subscriber_receives_initial_state_and_transitions(self) -> None:
        machine = SystemStateMachine(SystemState.READY)

        async with machine.subscribe() as updates:
            initial = await updates.get()
            await machine.transition(SystemState.CONTROLLED, "Driver acquired control")
            changed = await updates.get()

        self.assertEqual(SystemState.READY, initial.system_state)
        self.assertEqual(SystemState.CONTROLLED, changed.system_state)

    async def test_slow_subscriber_receives_only_latest_state(self) -> None:
        machine = SystemStateMachine(SystemState.READY)

        async with machine.subscribe() as updates:
            await machine.transition(SystemState.CONTROLLED, "Driver acquired control")
            await machine.transition(SystemState.READY, "Driver released control")
            latest = await updates.get()

        self.assertEqual(SystemState.READY, latest.system_state)
        self.assertEqual("Driver released control", latest.reason)
