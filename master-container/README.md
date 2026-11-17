# Master container

The Master API runs on port 8000 and sends steering, motor, and stream
commands to the existing Controller and Video APIs. The Docker image uses
real HTTP connections by default. No code changes are needed in those containers.

On startup, Master checks both services and enters `READY` when they respond.
It also checks them every second while running. If either becomes unavailable
during a driving lease, Master revokes control, latches emergency stop, and
attempts neutralization.
If either service starts later, requesting a control lease checks again.
You do not need to call a health endpoint before driving.
`GET /ping` returns `{"status":"ok"}`; it checks the Master process only.

## Deploy and test on the Pi

After uploading `master-api-pi.tar.gz` to `/home/nick`, back up the old files
and extract inside the existing `CC` folder:

```bash
cd /home/nick/CC
tar -czf "master-backup-$(date +%Y%m%d-%H%M%S).tar.gz" master-container &&
tar -xzf /home/nick/master-api-pi.tar.gz
python3 master-container/deploy.py
```

`deploy.py` finds the Compose file in the parent folder, builds only Master,
runs the offline tests, and restarts only Master if those tests pass. It always
includes `compose.server.yaml` so the Video host mapping is present. Finally it
checks the live `/ping`, readiness, and telemetry endpoints without sending
movement or stream commands. Controller and Video must already be running.
Live checks also verify background monitoring and saved event/telemetry history.
A failed live check returns a nonzero exit code and leaves the updated Master
running for diagnosis; it does not automatically roll back.

For a Compose file elsewhere, pass `--compose /path/to/docker-compose.yml`.
Its `master-api` build context must point to the uploaded `master-container`.
The initial image build may need internet access to obtain Python and packages.

To rerun the offline tests at any time after building the image:

```bash
python3 /home/nick/CC/master-container/offline_test.py --docker
```

This uses the existing `master-api-image:latest` image for dependencies and
tests the uploaded source with simulated Controller and Video services. It
does not pull images, publish ports, access devices, or contact the running
stack. Docker networking is disabled. Use `--image IMAGE_NAME` if your image
has a different name. Keep `tests/`, `offline_test.py`, and `deploy.py` on the Pi
to use these scripts.

On a computer where `requirements.txt` is already installed, you can also run
`python offline_test.py` from `master-container`. Tests cover motion forwarding,
leases, expiry, emergency stop, video commands, telemetry, startup recovery,
and deployment command scope. A passing offline test does not prove physical
movement, camera output, or Pi networking.

## Server connections

Your `/home/nick/CC/docker-compose.yml` uses these connections:

| Service | How the Master reaches it |
| --- | --- |
| Controller (`controller-api`) | Docker network, `http://controller-api:8002` |
| Video (`video-api`, host networking) | Host gateway, `http://host.docker.internal:8001` |
| Master (`master-api`) | Published port `8000` |

Copy the updated `master-container` folder to `/home/nick/CC/master-container`.
The included override supplies HTTP mode, the two URLs, and the host gateway
mapping. Use it with the server's existing Compose file:

```bash
cd /home/nick/CC
docker compose -f docker-compose.yml -f master-container/compose.server.yaml up -d --build --no-deps --wait master-api
docker compose -f docker-compose.yml logs --tail=50 master-api
curl http://127.0.0.1:8000/ping
curl http://127.0.0.1:8000/api/v1/health/ready
```

This rebuilds only `master-api`. Controller, Video, and MediaMTX must already
be running. If the same environment and `extra_hosts` settings have been added
to the main Compose file, the second `-f` is optional.

The root Compose file is intentionally ignored by Git. The Master override is
tracked here so it can be deployed with this folder. The old standalone
three-container Compose file has been removed in favor of your server stack.

## Basic movement tests

Run these on the server, one at a time, with the drive wheels raised initially:

```bash
cd /home/nick/CC/master-container
python3 drive_test.py ping
python3 drive_test.py left
python3 drive_test.py right
python3 drive_test.py forward
```

`left` and `right` apply 11.25 degrees of steering without driving the motor.
`forward` uses 10% normalized throttle (35 microseconds of PWM adjustment).
Each test holds for about half a second after acknowledgement, then sends
neutral, which also centers the steering. Low throttle may be below the motor's
starting threshold; an HTTP acknowledgement is not proof of physical movement.

The script checks readiness, obtains a lease, sends motion, renews the lease,
and releases it. It refuses to send movement in mock mode. To run from your
computer, use Python and the server's WireGuard address:

```powershell
python .\master-container\drive_test.py forward --url http://SERVER_WIREGUARD_IP:8000
```

To request a latched stop, or reset it once the car is safe:

```bash
python3 drive_test.py stop
python3 drive_test.py reset
```

Reverse is not included in this tester: the current Controller `/backward`
route calls `movement.backward`, while its function is named `backwards`.
That needs to be corrected in the Controller project by its owner.

## Endpoints and code

Open `http://SERVER_WIREGUARD_IP:8000/docs` for request schemas.

| Master endpoint | Behavior |
| --- | --- |
| `GET /ping` | Master reachability |
| `GET /api/v1/health/ready` | Checks both services; returns `503` with component details when unavailable |
| `POST /api/v1/control/lease` | Takes `{"client_id":"driver"}` and grants one driver control |
| `POST /api/v1/control/lease/heartbeat` | Renews control using `X-Control-Lease` |
| `PUT /api/v1/control/motion` | Requires lease; sends Controller `/steer` and `/forward`, `/backward`, or `/neutral` |
| `DELETE /api/v1/control/lease` | Requires lease; sends `/neutral` and releases control |
| `POST /api/v1/control/emergency-stop` | Invalidates control and sends `/neutral` |
| `POST /api/v1/control/emergency-stop/reset` | Checks dependencies and sends neutral before clearing the latch |
| `GET /api/v1/video/status` | Calls Video `/status` |
| `POST /api/v1/video/stream/start` | Calls Video `/stream/start` |
| `POST /api/v1/video/stream/stop` | Calls Video `/stream/stop` |
| `GET /api/v1/telemetry` | Combines controller state and video status |
| `GET /api/v1/telemetry/history` | Saved telemetry samples |
| `WS /api/v1/telemetry/ws` | Live samples for spectators |
| `GET /api/v1/system/events` | Saved request outcomes, errors, and state changes |
| `GET /api/v1/system/monitoring` | Background polling status and latest dependency checks |
| `GET /api/v1/video/recordings/current` | Recording status or `unsupported` for the current Video API |
| `POST /api/v1/video/recordings` | Requires lease and a UUID `request_id`; forwards a recording start |
| `DELETE /api/v1/video/recordings/{recording_id}` | Requires lease; stops that recording only |

For frontend integration, motion contains `steering` and `throttle` in [-1, 1],
an increasing `sequence`, and a `client_sent_at` timestamp. Renew the lease
every 0.5 seconds during driving; motion itself does not renew it. The default
lease expires after two seconds. Startup and lease acquisition handle readiness
automatically; the tester also checks readiness to report connection problems.

Read the implementation in this order:

1. `master_api/main.py`: registers routes and selects HTTP or mock clients.
2. `master_api/api/control.py` and `api/video.py`: public endpoints.
3. `master_api/clients/http.py`: actual outgoing HTTP requests.
4. `master_api/lease.py`: ownership, sequence checks, and stop requests.
5. `master_api/dependencies.py` and `journal.py`: background monitoring and history.

## History and live telemetry

The deployment override mounts a Docker volume at `/data`. Master saves events
and telemetry in `/data/master-history.sqlite3`, retaining the newest 10,000 of
each. The volume survives a Master restart or rebuild. Direct Python runs use
in-memory history unless `MASTER_API_HISTORY_PATH` is set.

Events include state transitions, dependency changes, request outcomes, and
downstream errors. Request bodies, query strings, lease tokens, and authorization
headers are not stored. Responses include `X-Request-ID` to find the corresponding
request event. History endpoints accept `after` (the last returned row ID) and
`limit` (1–1000); use `next_after` for the next page. Rows are oldest first.

Telemetry is sampled every second and pushed to WebSocket viewers. Slow viewers
receive the latest sample. When a component fails, its previous value is retained
and listed in `stale_components`; `observed_at` keeps the last successful fetch
time. With no previous sample the value is null. These timestamps describe Master
fetches, not sensor sampling times. Clients must check the stale flags. A snapshot
can return HTTP 200 with stale data; readiness still returns 503 on dependency failure.

Configure the polling interval with `MASTER_API_MONITOR_INTERVAL_SECONDS` and
retention with `MASTER_API_HISTORY_LIMIT`. Monitoring reports disk-write failures
without preventing a stop request.

## Recording integration

The current Video service only supports streaming. Master now has recording
routes, but actual recording requires its owner to implement the contract in
[VIDEO_RECORDING_CONTRACT.md](VIDEO_RECORDING_CONTRACT.md). Until then, recording
status is `unsupported` and recording mutations return HTTP 501. No Controller
or Video changes are included in this Master update.

Use the active `X-Control-Lease` for recording mutations. Send a fresh UUID as
`request_id` when starting; reuse it when retrying the same request. Stop using
the returned `recording_id`. After an ambiguous timeout, Master checks recording
status once instead of blindly repeating the command. Idempotency and persistent
video files are the Video service's responsibility.

## Read-only live checks

After deployment, run on the Pi:

```bash
python3 /home/nick/CC/master-container/live_test.py
```

Or from this computer:

```powershell
python .\master-container\live_test.py --url http://10.0.0.51:8000
```

This checks health, monitoring, telemetry, history, and recording capability.
It sends no movement or video commands. Offline tests exercise recording against
simulated services; an `unsupported` live result does not verify real recording.

## Configuration and limits

The Docker image and `compose.server.yaml` enable HTTP mode. Running Python
directly defaults to mocks unless `MASTER_API_CLIENT_MODE=http` is set.
Set `MASTER_API_CLIENT_MODE=mock` explicitly to use mocks in Docker. The optional
`server.env.example` lists the connection settings, but is not loaded automatically.

Controller HTTP deadlines default to 0.5 seconds per phase. Video start/stop
use an 8-second read timeout because the Video API waits for ffmpeg. These
longer waits do not change controller deadlines.

Use one Uvicorn worker and one Master instance: leases live in process memory.
The API has no user authentication; keep access limited to trusted WireGuard
peers. Lease expiry, release, shutdown with an active lease, and failed motion
attempt neutralization. They cannot stop hardware across a broken network or
after the Master is killed. The Controller needs its own watchdog for that.
Heartbeat renewal alone does not detect a frozen joystick. These are bench-test
tools, not a verified complete driving safety system.

## Local checks

```bash
cd master-container
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m uvicorn master_api.main:app
```

Tests exercise API routes and HTTP adapters with simulated peers. They do not
verify Raspberry Pi devices, WireGuard routing, or physical car movement.
