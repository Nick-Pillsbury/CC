"""Run one short movement through the Master API; requires only Python 3."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base_url, method, path, body=None, lease_id=None):
    headers = {"Content-Type": "application/json"}
    if lease_id:
        headers["X-Control-Lease"] = lease_id
    data = None if body is None else json.dumps(body).encode()
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            payload = response.read()
            return json.loads(payload) if payload else None
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {error.code}: {detail}") from error


def move(base_url, action):
    health = request(base_url, "GET", "/api/v1/health/ready")
    if not health["ready"]:
        raise RuntimeError("Controller/video are not ready.")
    if any("mock" in check["detail"] for check in health["checks"].values()):
        raise RuntimeError("Master is using mocks. Set MASTER_API_CLIENT_MODE=http.")

    lease = request(base_url, "POST", "/api/v1/control/lease", {"client_id": "drive-test"})
    lease_id = lease["lease_id"]
    steering, throttle = {"forward": (0.0, 0.1), "left": (-0.25, 0.0),
                          "right": (0.25, 0.0)}[action]
    try:
        request(base_url, "PUT", "/api/v1/control/motion", {
            "steering": steering, "throttle": throttle, "sequence": 1,
            "client_sent_at": datetime.now(timezone.utc).isoformat(),
        }, lease_id)
        # Hold for half a second, renewing ownership during the short test.
        for _ in range(2):
            time.sleep(0.25)
            request(base_url, "POST", "/api/v1/control/lease/heartbeat", lease_id=lease_id)
    finally:
        try:
            request(base_url, "DELETE", "/api/v1/control/lease", lease_id=lease_id)
        except (RuntimeError, URLError, TimeoutError):
            # If release cannot be confirmed, request a latched stop.
            request(base_url, "POST", "/api/v1/control/emergency-stop")
            print("Emergency stop requested; use reset before another test.")
    print("Controller acknowledged neutral. Test finished.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["ping", "forward", "left", "right", "stop", "reset"])
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Master API address")
    args = parser.parse_args()
    try:
        if args.action == "ping":
            print(request(args.url, "GET", "/ping"))
        elif args.action in {"stop", "reset"}:
            path = "/api/v1/control/emergency-stop"
            if args.action == "reset":
                path += "/reset"
            print(request(args.url, "POST", path))
        else:
            move(args.url, args.action)
    except (RuntimeError, URLError, TimeoutError) as error:
        print(f"Test failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Test interrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
