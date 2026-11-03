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
commands are rejected unless the state is `CONTROLLED`. A short-lived exclusive
control lease owns the `READY` to `CONTROLLED` transition and automatically
neutralizes the car when it expires or is released.
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

### Deploy into an existing server Compose stack

GitHub is not part of the runtime path. Copy this `master-container` directory
to the server over SSH/WireGuard, then make sure the server's existing Compose
service builds that directory and supplies these values:

```yaml
services:
  master:
    build: ./master-container
    environment:
      MASTER_API_CLIENT_MODE: http
      MASTER_API_CONTROLLER_BASE_URL: http://CONTROLLER_WIREGUARD_IP:8002
      MASTER_API_VIDEO_BASE_URL: http://VIDEO_WIREGUARD_IP:8001
      MASTER_API_CONTROL_LEASE_SECONDS: 2.0
    ports:
      - "8000:8000"
```

Rebuild only the Master service using the service name from the server's
Compose file:

```bash
docker compose up -d --build master
docker compose ps master
docker compose logs --tail=100 master
```

From another WireGuard peer, `GET /ping` verifies that the server and Master
API are reachable without calling the car:

```bash
curl http://SERVER_WIREGUARD_IP:8000/ping
curl http://SERVER_WIREGUARD_IP:8000/api/v1/health/ready
```

The readiness request must succeed before control can be acquired. It verifies
both downstream APIs and moves the system from `STARTING` to `READY`.

### Test-drive control sequence

Acquire exclusive control and save the returned `lease_id`:

```bash
curl -X POST http://SERVER_WIREGUARD_IP:8000/api/v1/control/lease \
  -H "Content-Type: application/json" \
  -d '{"client_id":"manual-test-driver"}'
```

The driver must send `POST /api/v1/control/lease/heartbeat` with the
`X-Control-Lease` header at least once every second. The default lease lasts two
seconds, so a lost client is neutralized quickly. Send increasing motion
sequence numbers through the same lease:

```bash
curl -X POST http://SERVER_WIREGUARD_IP:8000/api/v1/control/lease/heartbeat \
  -H "X-Control-Lease: LEASE_ID"

curl -X PUT http://SERVER_WIREGUARD_IP:8000/api/v1/control/motion \
  -H "Content-Type: application/json" \
  -H "X-Control-Lease: LEASE_ID" \
  -d '{"steering":0.0,"throttle":0.15,"sequence":1,"client_sent_at":"2026-11-03T12:00:00Z"}'
```

Stop and release control explicitly when the test ends:

```bash
curl -X DELETE http://SERVER_WIREGUARD_IP:8000/api/v1/control/lease \
  -H "X-Control-Lease: LEASE_ID"
```

`POST /api/v1/control/emergency-stop` is available without a lease so another
client can request an immediate neutral command. Reset requires both downstream
services to be healthy:

```bash
curl -X POST http://SERVER_WIREGUARD_IP:8000/api/v1/control/emergency-stop
curl -X POST http://SERVER_WIREGUARD_IP:8000/api/v1/control/emergency-stop/reset
```

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
| `MASTER_API_CONTROL_LEASE_SECONDS` | `2.0` |

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
