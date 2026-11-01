# Video Capture and Streaming Container

Part of **CC — Cellular-Controlled Car**. This document covers the tools, design decisions, configuration, and architecture of the Video Capture and Streaming Container.

---

## Overview

This stack runs on the car's Raspberry Pi 5 and consists of two containers:

- **camera-api**: a FastAPI service that captures video from a USB webcam, encodes it to H.264 with FFmpeg, and publishes it to MediaMTX. It also records to a USB drive.
- **mediamtx**: ingests the RTSP feed from FFmpeg (locally) and serves it to the driver over **WebRTC**.

The stream reaches the driver through the **WireGuard tunnel** over the car's cellular connection. The design priority is **lowest possible latency for a single driver**. Multi-viewer scaling was intentionally dropped in favor of speed.

The Master API controls this container through its HTTP API: start/stop streaming, start/stop recording, and check health. The container also protects recordings by refusing to stop the stream while a recording is in progress.

---

## Functionality

This container is responsible for:

- Receiving control commands from the Master API
- Capturing live video from a USB webcam (MJPEG, 1920x1080 @ 30 fps)
- Encoding video to H.264 (tuned for low latency)
- Streaming video via WebRTC to the Frontend
- Recording video to persistent storage for playback
- Monitoring container and stream health
- Reporting errors back to the Master API

---

## Who Uses the Stream

| Consumer | Purpose |
|---|---|
| **Driver view** (Frontend, shown on Meta Quest via HDMI passthrough) | Live POV with status and telemetry overlays |
| **Master API** | Starts/stops streaming and recording, reads health and errors |

> Spectator video is not a priority. If added later, MediaMTX can serve a few extra viewers, or spectators can use a higher-latency HLS stream.

---

## Tools and Technology Stack

### 1. Python FastAPI
Matches the Master API so all services use the same patterns. Easy to develop and maintain, and well supported.

### 2. FFmpeg
Captures from V4L2, encodes H.264 with low-latency tuning, and publishes over RTSP. A second FFmpeg process records the stream to disk without re-encoding.

### 3. MediaMTX
- Built-in WebRTC (WHEP) support, so the Frontend can play the stream in a browser with no extra client
- Low resource usage (important on a Raspberry Pi)
- Ingests RTSP from FFmpeg and re-serves it over WebRTC

### 4. WebRTC
- Designed for sub-200 ms latency, which matters when driving
- Media runs over UDP, which handles cellular jitter and packet loss better than TCP-based protocols
- Plays natively in browsers

### 5. RTSP (local ingest only)
FFmpeg publishes to MediaMTX over RTSP on the Pi itself, so this hop adds no meaningful latency. The latency-sensitive leg is the WebRTC connection over cellular.

- **Ingest URL:** `rtsp://127.0.0.1:8554/stream`
- RTSP is bound to `127.0.0.1` and is not reachable from other devices.

### 6. H.264
High compression efficiency, low bandwidth, and wide WebRTC support. WebRTC does not carry MJPEG, so the camera's MJPEG output is always transcoded to H.264.

### 7. WireGuard
Carries the stream and API traffic between the car and the rest of the system over the cellular network. Encrypted, and reachable from anywhere with cell coverage. Viewers are WireGuard peers and connect directly to the Pi's tunnel IP.

### 8. Docker
- Hardware device access (`/dev/video0`, USB storage)
- Service isolation between system components
- Consistent environment across development and deployment
- Modular architecture, so each component can be developed and tested independently

---

## Camera Input

The webcam outputs **MJPEG at 1920x1080 @ 30 fps** (discrete, 0.033 s interval). It is connected over USB 2 (480M), which is more than enough for compressed MJPEG, so a USB 3 port is not required.

Check what your camera supports:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

A UVC camera usually creates two device nodes. The first (`/dev/video0`) is the capture node, the second is metadata.

---

## Encoding on the Raspberry Pi 5

The Pi 5 has **no hardware H.264 encoder**, so encoding is done in software (x264) on the CPU. The settings below keep latency and CPU use low:

| Setting | Value | Why |
|---|---|---|
| Input format | `mjpeg`, 1920x1080 @ 30 | What the camera provides natively |
| Preset | `ultrafast` | Lowest encode time |
| Tune | `zerolatency` | Disables lookahead and frame reordering |
| Profile | `baseline` | Compatible with browser WebRTC |
| B-frames | `-bf 0` | No frame reordering, lowest latency |
| Keyframe interval | `-g 30` (~1 second) | Fast recovery after packet loss |
| Repeat headers | `repeat-headers=1` | SPS/PPS on every keyframe so viewers can join mid-stream |
| Timestamps | `-use_wallclock_as_timestamps 1` | Avoids V4L2 MJPEG timestamp drift |
| Bitrate | `3M` cap, `1500k` bufsize | Prevents stalls on weak cellular signal |

Example FFmpeg command (what the API runs):

```bash
ffmpeg -loglevel warning \
  -fflags nobuffer -flags low_delay -use_wallclock_as_timestamps 1 \
  -f v4l2 -input_format mjpeg -video_size 1920x1080 -framerate 30 \
  -i /dev/video0 -an \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -profile:v baseline -pix_fmt yuv420p \
  -g 30 -bf 0 -x264-params repeat-headers=1 \
  -b:v 3M -maxrate 3M -bufsize 1500k \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/stream
```

**If CPU use or bandwidth is too high**, lower the load with environment variables:

- `VIDEO_SIZE=1280x720` cuts encode cost and bitrate needs significantly
- `BITRATE=1.5M` for weak cellular signal

---

## Stream Architecture

```plaintext
      USB Webcam (/dev/video0, MJPEG 1080p30)
                    ↓
        FFmpeg (x264, low-latency)
                    ↓
        RTSP (local, 127.0.0.1:8554)
                    ↓
                 MediaMTX 
                    ↓
        WebRTC over WireGuard
        (cellular connection)
                    ↓
        Frontend (Driver view)
```

---

## API Reference

The service listens on port `8000`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/stream/start` | Start capture, encode, and publish to MediaMTX |
| `POST` | `/stream/stop` | Stop the stream (refused while recording) |
| `POST` | `/recording/start` | Start recording the live stream to a new file |
| `POST` | `/recording/stop` | Stop recording and close the file cleanly |
| `GET` | `/status` | Stream and recording state, current recording file |
| `GET` | `/health` | Camera, MediaMTX, storage, process state, and last error |

Notes:

- **The stream must be started before anyone can watch it.** The WebRTC page loads with no stream, but no video appears until `POST /stream/start` is called.
- **Recording requires a running stream.** It reads from the RTSP feed, so the stream must be started first.
- **Stream stop is blocked during a recording.** Stop the recording first, otherwise the recording process would error out.
- The API has **no authentication**. Access control is the WireGuard tunnel, so only give the tunnel to trusted peers.

Example `GET /health` response:

```json
{
  "ok": true,
  "camera_detected": true,
  "mediamtx_reachable": true,
  "storage_writable": true,
  "stream": "running",
  "recording": "stopped",
  "last_error": null
}
```

---

## Recording

- Recording copies the already-encoded H.264 stream (`-c:v copy`), so it adds almost no CPU load.
- Files are saved as `recording_YYYYMMDD_HHMMSS.mp4` in `/recordings` (mapped to `/mnt/usb` on the host).
- **Fragmented MP4** (`frag_keyframe+empty_moov+default_base_moof`) keeps the file playable if the Pi loses power mid-recording.
- Stopping sends `SIGINT` to FFmpeg so it can finish and close the file cleanly.
- Recording is local, so it keeps working if the cellular connection drops.
- Audio is not recorded (`-an`).

---

## Video Storage

An external USB 3.0 thumb drive is used because:

- Recording sessions are short
- It is very cheap
- It preserves the microSD card by avoiding heavy read/write wear

`/mnt/usb` must be mounted on the host before the container starts. If it is not, Docker creates an empty directory there and recordings land on the SD card.

---

## Deployment

### Project layout

```
Video/
├── Dockerfile
├── docker-compose.yml
├── mediamtx.yml
├── requirements.txt
└── main.py
```

### Services

Both services use `network_mode: host`. The API talks to MediaMTX at `127.0.0.1:8554`, and WebRTC needs UDP ports, so host networking is the simplest setup.

| Service | Image | Ports (host) |
|---|---|---|
| `mediamtx` | `bluenviron/mediamtx:1` | `8889/tcp` (WebRTC signaling), `8189/udp` (WebRTC media), `8554/tcp` (RTSP, localhost only) |
| `camera-api` | built from `Dockerfile` | `8000/tcp` (API) |

### Configuration (environment variables)

Set these on `camera-api` in `docker-compose.yml`.

| Variable | Default | Description |
|---|---|---|
| `CAMERA_DEVICE` | `/dev/video0` | Camera device path |
| `VIDEO_SIZE` | `1920x1080` | Capture resolution |
| `FRAMERATE` | `30` | Capture frame rate (also sets keyframe interval) |
| `BITRATE` | `3M` | Video bitrate cap |
| `BUFSIZE` | `1500k` | Encoder buffer size (~0.5 s keeps latency low) |
| `RTSP_PORT` | `8554` | Local RTSP ingest port |
| `RECORDINGS_DIR` | `/recordings` | Recording output directory in the container |

### MediaMTX key settings

```yaml
rtspAddress: 127.0.0.1:8554        # local ingest only
webrtcAddress: :8889
webrtcLocalUDPAddress: :8189
webrtcAdditionalHosts:
  - 10.0.0.52                      # the Pi's WireGuard IP

paths:
  stream:
    source: publisher
```

`webrtcAdditionalHosts` is the address the viewer's browser is told to send WebRTC media to, so it must be the **Pi's** WireGuard IP.

### Run

```bash
docker compose up -d --build
docker compose logs -f
```

### Stable camera path

`/dev/video0` can change between reboots or when the camera is replugged. For a fixed path, map the stable symlink from the host while keeping `/dev/video0` inside the container:

```yaml
devices:
  - /dev/v4l/by-id/usb-YourCamera-video-index0:/dev/video0
```

Find the right name with `ls -l /dev/v4l/by-id/`.

---

## Viewing the Stream

The viewer must be connected to the WireGuard tunnel.

| Method | URL |
|---|---|
| Browser (WebRTC player) | `http://10.0.0.52:8889/stream` |
| WHEP endpoint (for the Frontend) | `http://10.0.0.52:8889/stream/whep` |

RTSP viewers (VLC, ffplay) are not enabled. To use them, set `rtspAddress: :8554` in `mediamtx.yml` and restart MediaMTX. This exposes RTSP to the whole tunnel.

---

## Health Monitoring and Errors

The container tracks and reports:

- Whether the camera is detected
- Whether MediaMTX is reachable
- Whether the stream FFmpeg process is running
- Whether a recording is active
- Whether recording storage is writable
- The last error, with the most recent FFmpeg log lines

FFmpeg crashes (including camera unplug) are detected automatically the next time any endpoint checks the process, and are recorded as `last_error`. The Master API reads `/health` and includes it in system-wide monitoring and telemetry.

---

## Troubleshooting

**Page loads but no video**

1. Confirm the stream is running: `curl http://10.0.0.52:8000/status`. If it is stopped, call `POST /stream/start`.
2. Watch MediaMTX logs while opening the page: `docker compose logs -f mediamtx`.
   - `no stream is available on path 'stream'` means the stream was not started.
   - `peer connection established` followed by `closed` means ICE or UDP is failing.
3. WebRTC media is UDP, so SSH working over the tunnel does not prove media will. If UDP is blocked, enable the TCP fallback in `mediamtx.yml` and restart:
   ```yaml
   webrtcLocalTCPAddress: :8189
   ```
4. Packets larger than the tunnel MTU are dropped silently. Set `MTU = 1280` in the `[Interface]` section of the Pi and viewer WireGuard configs.
5. In Chrome, open `chrome://webrtc-internals` and check that `10.0.0.52:8189` appears among the ICE candidates.

**Stream fails to start**

- Camera busy or wrong format: check `last_error.details` in `/health`, and confirm the camera lists MJPG at 1920x1080 with `v4l2-ctl --list-formats-ext`.
- Camera not found: check `ls /dev/video*` and the `devices:` entry in the compose file.

**Recording fails to start**

- Check that `/mnt/usb` is mounted on the host and writable (`storage_writable` in `/health`).

**High CPU**

- Check with `htop` while streaming. Reduce `VIDEO_SIZE` to `1280x720` if needed.

---

## Docker Commands

> Container Controls
> ```
> docker start <container>
> docker stop <container>
> docker restart <container>
> docker rm <container>
> docker logs <container>
> docker exec -it <container> bash
> ```
>
> List containers
> ```
> docker ps
> ```
>
> Compose
> ```
> docker compose up -d
> docker compose down
> docker compose restart
> docker compose logs -f
> ```