# CC
The goal of CC is to design and implement a cellular-enabled RC car, modified to run off a Raspberry Pi, for remote driving from anywhere with cell coverage.

## Master API

The Master API exposes endpoints for motion control, video recording, telemetry,
liveness, and readiness. It uses in-memory mock clients by default so the API and
frontend can run without the hardware and video containers. Set
`MASTER_API_CLIENT_MODE=http` to forward the same routes to the downstream HTTP
services; route code does not change between modes.

Install and run it with:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn master_api.main:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

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
