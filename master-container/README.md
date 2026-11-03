# Master container

The Master API receives requests on port 8000 and forwards them to the
Controller and Video APIs. `GET /ping` returns `{"status":"ok"}`; it checks
the Master process only, not the car.

## Deploy with your server's Compose file

Your `/home/nick/compose.yaml` uses these connections:

| Service | How the Master reaches it |
| --- | --- |
| Controller (`controller-api`) | Docker network, `http://controller-api:8002` |
| Video (`video-api`, host networking) | Host gateway, `http://host.docker.internal:8001` |
| Master (`master-api`) | Published port `8000` |

Copy the updated `master-container` folder to `/home/nick/master-container`.
The included override supplies HTTP mode, the two URLs, and the host gateway
mapping. Use it with the server's existing Compose file:

```bash
cd /home/nick
docker compose -f compose.yaml -f master-container/compose.server.yaml up -d --build --no-deps master-api
docker compose logs --tail=50 master-api
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
cd /home/nick/master-container
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
| `GET /api/v1/health/ready` | Calls both downstream `/status` routes; healthy checks enable `READY` state |
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

For frontend integration, motion contains `steering` and `throttle` in [-1, 1],
an increasing `sequence`, and a `client_sent_at` timestamp. Renew the lease
every 0.5 seconds during driving; motion itself does not renew it. The default
lease expires after two seconds. The readiness call currently precedes lease
acquisition; the tester handles that automatically.

Read the implementation in this order:

1. `master_api/main.py`: registers routes and selects HTTP or mock clients.
2. `master_api/api/control.py` and `api/video.py`: public endpoints.
3. `master_api/clients/http.py`: actual outgoing HTTP requests.
4. `master_api/lease.py`: ownership, sequence checks, and stop requests.

## Configuration and limits

Without `MASTER_API_CLIENT_MODE=http`, the app uses mocks and never contacts
the car. `compose.server.yaml` explicitly enables HTTP mode. The optional
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
