"""Recording ownership, retries, unsupported peers, and timeout reconciliation."""

import json
import unittest
from uuid import uuid4

import httpx

from master_api.clients.errors import DownstreamResponseError, DownstreamTimeoutError, RecordingUnsupportedError
from master_api.clients.http import HttpVideoClient
from tests.base import ApiTestCase


class RecordingEndpointTests(ApiTestCase):
    def acquire(self):
        lease = self.client.post("/api/v1/control/lease", json={"client_id": "driver"}).json()
        return {"X-Control-Lease": lease["lease_id"]}

    def test_recording_requires_active_lease(self):
        body = {"request_id": str(uuid4())}
        self.assertEqual(422, self.client.post("/api/v1/video/recordings", json=body).status_code)
        self.assertEqual(409, self.client.post("/api/v1/video/recordings", json=body,
                                              headers={"X-Control-Lease": "invalid"}).status_code)

    def test_retries_do_not_restart_recordings_or_stop_a_newer_one(self):
        headers = self.acquire()
        first, second = str(uuid4()), str(uuid4())
        start = lambda rid: self.client.post("/api/v1/video/recordings", headers=headers,
                                            json={"request_id": rid})
        stop = lambda rid: self.client.delete(f"/api/v1/video/recordings/{rid}", headers=headers)
        original = start(first).json()
        self.assertEqual(original, start(first).json())
        self.assertEqual(409, start(second).status_code)
        self.assertEqual("stopped", stop(first).json()["state"])
        self.assertEqual("stopped", start(first).json()["state"])
        self.assertEqual("recording", start(second).json()["state"])
        self.assertEqual("stopped", stop(first).json()["state"])
        current = self.client.get("/api/v1/video/recordings/current").json()
        self.assertEqual(second, current["recording_id"])
        self.assertEqual("recording", current["state"])
        self.assertEqual(second, self.client.get("/api/v1/telemetry").json()["recording"]["recording_id"])


class RecordingHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_video_reports_unsupported_without_pretending_to_record(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as http:
            video = HttpVideoClient(http, "http://video")
            self.assertEqual("unsupported", (await video.recording_status()).state)
            with self.assertRaises(RecordingUnsupportedError):
                await video.start_recording(uuid4())

    async def test_timeout_is_reconciled_without_replaying_start(self):
        request_id = uuid4()
        requests = []

        def handler(request):
            requests.append(request)
            if request.method == "POST":
                self.assertEqual(str(request_id), json.loads(request.content)["request_id"])
                self.assertEqual(8, request.extensions["timeout"]["read"])
                raise httpx.ReadTimeout("acknowledgement lost", request=request)
            return httpx.Response(200, json={"state": "recording", "recording_id": str(request_id)})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            result = await HttpVideoClient(http, "http://video").start_recording(request_id)
            self.assertEqual(request_id, result.recording_id)
            self.assertEqual(["POST", "GET"], [r.method for r in requests])

    async def test_ambiguous_timeout_remains_error(self):
        def handler(request):
            if request.method == "POST":
                raise httpx.ReadTimeout("lost", request=request)
            return httpx.Response(200, json={"state": "idle"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with self.assertRaises(DownstreamTimeoutError):
                await HttpVideoClient(http, "http://video").start_recording(uuid4())

    async def test_wrong_recording_acknowledgement_is_rejected(self):
        handler = lambda r: httpx.Response(200, json={"state": "recording", "recording_id": str(uuid4())})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with self.assertRaises(DownstreamResponseError):
                await HttpVideoClient(http, "http://video").start_recording(uuid4())
