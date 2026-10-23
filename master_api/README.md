# CC
The goal of CC is to design and implement a cellular-enabled RC car, modified to run off a Raspberry Pi, for remote driving from anywhere with cell coverage.

## Master API

The Master API exposes endpoints for motion control, video recording, telemetry,
liveness, and readiness. It uses in-memory mock clients by default so the API and
frontend can run without the hardware and video containers. Set
`MASTER_API_CLIENT_MODE=http` to forward the same routes to the downstream HTTP
services; route code does not change between modes.

The process owns an explicit system state (`STARTING`, `READY`, `CONTROLLED`,
`DEGRADED`, `EMERGENCY_STOP`, or `SHUTTING_DOWN`). Dependency health updates
that state, `GET /api/v1/system/state` exposes the latest transition, and motion
commands are rejected unless the state is `CONTROLLED`. Control-lease endpoints
will own the `READY` to `CONTROLLED` transition in the next implementation phase.
Clients can subscribe to `WS /api/v1/system/state/ws` to receive the current
state immediately and every later transition. Each subscriber uses a bounded
latest-value queue, so a slow frontend cannot block command or health handling.

From the `CC` repository folder, install and run it with:

```powershell
Set-Location master_api
python -m pip install -r requirements.txt
python -m uvicorn master_api.main:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### Project layout

The two `master_api` names have different purposes: the outer folder is the
project folder, while the inner folder is the importable Python package.

```text
CC/
└── master_api/              # Project folder
    ├── master_api/          # Python application package
    │   ├── api/             # HTTP and WebSocket routes
    │   ├── clients/         # Hardware and video integrations
    │   ├── main.py          # FastAPI setup and startup/shutdown
    │   ├── models.py        # Request and response data models
    │   └── state.py         # Safety-related system state
    ├── tests/               # Automated tests
    ├── Research/            # Design notes and interface drafts
    └── requirements.txt     # Python dependencies
```

### Downstream HTTP configuration

The hardware and video clients share one application-scoped asynchronous HTTP
connection pool. The pool is created during application startup and closed during
shutdown. Configure HTTP mode before starting Uvicorn:

```powershell
$env:MASTER_API_CLIENT_MODE = "http"
$env:MASTER_API_HARDWARE_BASE_URL = "http://hardware:8000"
$env:MASTER_API_VIDEO_BASE_URL = "http://video:8000"
python -m uvicorn master_api.main:app --reload
```

All supported settings are environment variables:

| Variable | Default |
| --- | --- |
| `MASTER_API_CLIENT_MODE` | `mock` |
| `MASTER_API_HARDWARE_BASE_URL` | `http://hardware:8000` |
| `MASTER_API_VIDEO_BASE_URL` | `http://video:8000` |
| `MASTER_API_HTTP_CONNECT_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_READ_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_WRITE_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_POOL_TIMEOUT_SECONDS` | `0.5` |

Timeouts return `504 downstream_timeout`, connection failures return
`503 downstream_unavailable`, and unsuccessful or invalid downstream responses
return a stable `502` error. The public error body does not include downstream
addresses, raw responses, or exception details.

Run the endpoint tests with:

```powershell
python -m unittest discover -s tests -v
```

## Development approach

Keep the implementation readable to an average computer science student. Clear,
ordinary code is more important than using the fewest lines. As safety permits:

- add behavior only when there is a current requirement or test for it;
- keep HTTP routes thin and put shared rules in focused modules;
- prefer the standard library and existing dependencies;
- prefer basic control flow over clever or advanced language features;
- introduce an abstraction only when it removes real duplication or isolates an
  external system;
- keep safety checks explicit, even when a shorter implementation is possible;
- test public behavior and failure cases instead of implementation details; and
- update this README when setup or behavior changes.
