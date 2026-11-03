"""Verify movement test cleanup without sending anything to a car."""

import unittest
from unittest.mock import patch

import drive_test


class DriveTestTests(unittest.TestCase):
    def run_test(self, fail_motion=False, mock_hardware=False):
        calls = []

        def request(base_url, method, path, body=None, lease_id=None):
            calls.append((method, path, body, lease_id))
            if path.endswith("/ready"):
                return {"ready": True, "checks": {"hardware": {
                    "detail": "mock hardware ready" if mock_hardware else "controller hardware ready",
                }}}
            if method == "POST" and path.endswith("/lease"):
                return {"lease_id": "test-lease"}
            if fail_motion and path.endswith("/motion"):
                raise RuntimeError("Controller failed")

        with patch("drive_test.request", side_effect=request), patch("drive_test.time.sleep"), patch("builtins.print"):
            if fail_motion or mock_hardware:
                with self.assertRaises(RuntimeError):
                    drive_test.move("http://master.test", "forward")
            else:
                drive_test.move("http://master.test", "forward")
        return calls

    def test_forward_uses_small_throttle_and_releases(self):
        calls = self.run_test()
        motion = next(call for call in calls if call[1].endswith("/motion"))
        self.assertEqual(0.1, motion[2]["throttle"])
        self.assertEqual("test-lease", motion[3])
        self.assertEqual(("DELETE", "/api/v1/control/lease"), calls[-1][:2])

    def test_failed_motion_still_releases(self):
        calls = self.run_test(fail_motion=True)
        self.assertEqual(("DELETE", "/api/v1/control/lease"), calls[-1][:2])

    def test_mock_mode_never_sends_motion(self):
        self.assertEqual(1, len(self.run_test(mock_hardware=True)))
