# CC
The goal of CC is to design and implement a cellular-enabled RC car, modified to run off a Raspberry Pi, for remote driving from anywhere with cell coverage.

## Master API

The Master API exposes endpoints for motion control, video streaming, telemetry,
liveness, and readiness. It uses in-memory mock clients by default so the API and
frontend can run without the Controller and Video APIs. Set
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
Set-Location master-container
python -m pip install -r requirements.txt
python -m uvicorn master_api.main:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### Docker

Build the image from the outer `master-container` project folder. The Dockerfile
installs every package listed in `requirements.txt` and copies the application
code into the image.

```bash
docker build -t cc-master-api .
```

Run it in HTTP mode and replace the example addresses with the WireGuard
addresses of the Controller and Video APIs:

```bash
docker run --rm -p 8000:8000 \
  -e MASTER_API_CLIENT_MODE=http \
  -e MASTER_API_CONTROLLER_BASE_URL=http://10.0.0.50:8002 \
  -e MASTER_API_VIDEO_BASE_URL=http://10.0.0.51:8001 \
  cc-master-api
```

Open `http://SERVER_WIREGUARD_IP:8000/docs` to view the API documentation.

### Run the three containers together

The included `compose.yaml` builds the existing sibling Controller and Video
projects without modifying or tracking them. Keep this local layout:

```text
CC/
+-- master-container/
+-- controller-container/
+-- video-container/
```

On the Raspberry Pi, start the stack from the Master project:

```bash
cd master-container
docker compose up --build -d
docker compose ps
```

The compose network resolves the services as `controller` and `video`. The
Master API runs in HTTP mode and connects to their actual internal ports:
Controller `8002` and Video `8001`. Only the Master API is published to the
host, on port `8000`; downstream API ports stay inside the compose network.

The default device mappings are `/dev/i2c-1` for the Controller and
`/dev/video0` for Video. Override a host device without editing the compose
file when necessary:

```bash
CC_I2C_DEVICE=/dev/i2c-0 CC_CAMERA_DEVICE=/dev/video2 docker compose up --build -d
```

Check the full path through the Master after the services start:

```bash
curl http://127.0.0.1:8000/api/v1/health/live
curl http://127.0.0.1:8000/api/v1/health/ready
curl http://127.0.0.1:8000/api/v1/video/status
```

`health/live` verifies the Master process. `health/ready` also calls both
downstream containers and returns `503` when the Controller reports that its
hardware is offline or either dependency cannot be reached.

### Project layout

The outer `master-container` folder is the container project, while the inner
`master_api` folder is the importable Python package.

```text
CC/
+-- master-container/       # Container project folder
    +-- master_api/          # Python application package
    |   +-- api/             # HTTP and WebSocket routes
    |   +-- clients/         # Controller and Video integrations
    |   +-- main.py          # FastAPI setup and startup/shutdown
    |   +-- models.py        # Request and response data models
    |   +-- state.py         # Safety-related system state
    +-- tests/               # Automated tests
    +-- Research/            # Design notes and interface drafts
    +-- Dockerfile           # Container build instructions
    +-- requirements.txt     # Python dependencies
```

### Downstream HTTP configuration

The Controller and Video clients share one application-scoped asynchronous HTTP
connection pool. The pool is created during application startup and closed during
shutdown. Configure HTTP mode before starting Uvicorn:

```powershell
$env:MASTER_API_CLIENT_MODE = "http"
$env:MASTER_API_CONTROLLER_BASE_URL = "http://controller:8002"
$env:MASTER_API_VIDEO_BASE_URL = "http://video:8001"
python -m uvicorn master_api.main:app --reload
```

All supported settings are environment variables:

| Variable | Default |
| --- | --- |
| `MASTER_API_CLIENT_MODE` | `mock` |
| `MASTER_API_CONTROLLER_BASE_URL` | `http://controller:8002` |
| `MASTER_API_VIDEO_BASE_URL` | `http://video:8001` |
| `MASTER_API_HTTP_CONNECT_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_READ_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_WRITE_TIMEOUT_SECONDS` | `0.5` |
| `MASTER_API_HTTP_POOL_TIMEOUT_SECONDS` | `0.5` |

The Master API translates its small public contract to the APIs that already
exist:

| Master API behavior | Downstream request |
| --- | --- |
| Check Controller health or read telemetry | `GET /status` |
| Apply steering | `POST /steer?deg=...` |
| Apply positive or negative throttle | `POST /forward?delta=...` or `POST /backward?delta=...` |
| Stop the motor | `POST /neutral` |
| Read Video status | `GET /status` |
| Start or stop video | `POST /stream/start` or `POST /stream/stop` |

Public steering and throttle values remain normalized from `-1.0` to `1.0`.
The adapter converts steering to `-45` through `45` degrees and throttle to the
Controller's `0` through `350` microsecond delta. It also converts the
Controller's lower-forward/higher-reverse PWM convention back to the public
API's positive-forward convention when reporting telemetry. The repository
intentionally tracks only `master-container/`; the sibling
`controller-container/` and `video-container/` folders are ignored.

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
