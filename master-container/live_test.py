"""Read-only checks of deployed Master. Does not send car or video commands."""

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def check(base_url: str) -> None:
    def get(path):
        with urlopen(base_url.rstrip("/") + path, timeout=10) as response:
            return json.load(response)

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    require(get("/ping")["status"] == "ok", "Master ping failed")
    ready = get("/api/v1/health/ready")
    require(ready["ready"], "Controller or Video is unavailable")
    print("PASS: Master, Controller, and Video are reachable", flush=True)

    # Give the first background sample time to arrive after a deployment.
    for _ in range(20):
        monitor = get("/api/v1/system/monitoring")
        if monitor["telemetry_sampled_at"]:
            break
        time.sleep(0.25)
    require(monitor["running"] and not monitor["health_stale"], "Background monitoring is not healthy")
    require(not any(monitor[key] for key in ("last_error", "telemetry_error", "history_error")),
            "Monitoring reported an error: " + json.dumps(monitor))
    require(monitor["telemetry_sampled_at"] is not None, "Background telemetry has not started")
    print("PASS: Background health and telemetry monitoring", flush=True)

    sample = get("/api/v1/telemetry")
    require(not sample["stale_components"] and sample["hardware"] is not None and sample["video"] is not None,
            "Telemetry is unavailable or stale: " + json.dumps(sample))
    require(bool(get("/api/v1/telemetry/history?limit=1")["items"]), "Telemetry history is empty")
    require(bool(get("/api/v1/system/events?limit=1")["items"]), "Event history is empty")
    print("PASS: Current telemetry and saved event/telemetry history", flush=True)

    recording = get("/api/v1/video/recordings/current")
    print("Video recording capability: " + recording["state"], flush=True)
    if recording["state"] == "unsupported":
        print("Recording cannot be tested until the Video owner implements the recording API.", flush=True)
    print("PASS: Live Master checks. No movement, stream, or recording commands sent.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        check(args.url)
    except HTTPError as exc:
        print(f"FAIL: HTTP {exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except (URLError, OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
