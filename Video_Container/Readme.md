# Video Capture and Streaming Container
Part of **CC — Cellular-Controlled Car**. This document outlines the tools, design decisions, configuration, and architecture of the Video Capture and Streaming Container.
 
---
 
## Overview
This container runs a FastAPI-based video service on the car's Raspberry Pi 5. It captures the car's point-of-view from a USB webcam, encodes it with FFmpeg (H.264), and publishes it to MediaMTX, which serves it to the driver over **WebRTC**. The stream travels over the WireGuard tunnel and the car's cellular connection.
 
The design priority is **lowest possible latency for a single driver**. Multi-viewer scaling was intentionally dropped in favor of speed.
 
The Master API controls this container through its own API: start/stop streaming, start/stop recording, and check health. The container also protects recordings by refusing to stop the stream while a recording is in progress.
 
---
 
## Functionality
This container is responsible for:
- Receiving control commands from the Master API
- Capturing live video from a USB webcam
- Encoding video using H.264 (tuned for low latency)
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
FastAPI was selected due to its ease of use and high compatibility. It's best for:
- Compatibility across clients and platforms
- Ease of development and maintenance
- Well-maintained and fast framework
- Matching the Master API, so all services use the same patterns
### 2. FFmpeg
FFmpeg was selected for video processing and streaming because it provides:
- H.264 encoding support
- Low-latency tuning options
- A well-known tool for capturing and streaming via multiple protocols
### 3. MediaMTX
MediaMTX was selected as the streaming server because of:
- Built-in WebRTC (WHEP) support, so the Frontend can play the stream in a browser with no extra client
- Low resource usage (important on a Raspberry Pi)
- Ability to ingest RTSP from FFmpeg and re-serve it over WebRTC
### 4. WebRTC
WebRTC was chosen as the delivery protocol because:
- Designed for sub-200 ms latency, which matters when driving
- Runs over UDP, which handles cellular jitter and packet loss better than TCP-based protocols
- Plays natively in browsers
### 5. RTSP (local ingest only)
FFmpeg publishes to MediaMTX over RTSP on the Pi itself. This hop is local, so it adds no meaningful latency. The latency-sensitive leg is the WebRTC connection over cellular.
 
**Default RTSP ingest port:** `8554`
 
### 6. H.264 Compression
H.264 was selected due to:
- High compression efficiency
- Low bandwidth usage, which is important over a cellular connection
- Wide WebRTC support
### 7. WireGuard
WireGuard carries the stream and API traffic between the car and the rest of the system, providing:
- Encrypted connection over the cellular network
- Reachability from anywhere with cell coverage
### 8. Docker
Docker was selected for containerization because it provides:
- Hardware device access support (`/dev/video0`, USB storage)
- Service isolation between system components
- Environment consistency across development and deployment
- Simplified dependency management
- Modular architecture, so each component can be developed and tested independently
---
 
## Encoding on the Raspberry Pi 5
The Pi 5 has **no hardware H.264 encoder**, so encoding is done in software (x264) on the CPU. Settings are chosen to make this as fast as possible:
 
| Setting | Value | Why |
|---|---|---|
| Preset | `ultrafast` | Lowest encode time |
| Tune | `zerolatency` | Disables B-frames and lookahead |
| Profile | `baseline` | Compatible with browser WebRTC |
| Resolution / FPS | 1280x720 @ 30 (or 640x480) | Keeps CPU load and bandwidth low |
| Keyframe interval | ~1 second (`-g 30`) | Fast recovery after packet loss |
| Bitrate | ~2 Mbps cap | Prevents stalls on weak cellular signal |
 
Example FFmpeg command:
```
ffmpeg -f v4l2 -framerate 30 -video_size 1280x720 -i /dev/video0 \
  -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline \
  -g 30 -b:v 2M -maxrate 2M -bufsize 1M \
  -f rtsp rtsp://localhost:8554/car
```
 
**Best optimization:** use a UVC webcam that outputs H.264 (or MJPEG) natively. This removes the software encode from the Pi entirely and gives the lowest latency and CPU load.
 
---
 
## Stream Architecture
```plaintext
     USB Webcam (/dev/video0)
              ↓
   FFmpeg (x264, low-latency)  ──────→ Recording (USB drive)
              ↓
     RTSP (local, port 8554)
              ↓
        MediaMTX Server
              ↓
      WebRTC over WireGuard
      (cellular connection)
              ↓
      Frontend (Driver view)
```
 
---
 
## Video Storage
An external USB 3.0 thumb drive was used because:
- Recording sessions are short
- It is very cheap
- It preserves the microSD card by avoiding heavy read/write wear
---
 
## Health Monitoring and Errors
The container tracks and reports:
- Whether the camera is detected
- Whether FFmpeg and MediaMTX are running
- Whether the stream is live
- Whether a recording is active
- Errors (camera disconnect, FFmpeg crash, storage unavailable, etc.)
The Master API reads this status and includes it in system-wide monitoring and telemetry.
 
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