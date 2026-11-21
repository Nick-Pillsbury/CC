# CC — Cellular-Controlled Car

A cellular-enabled RC car run by a Raspberry Pi 5, driven remotely from anywhere with cell coverage. The driver wears a Meta Quest (HDMI passthrough) and steers with an Xbox controller while watching the car's live camera feed. All traffic runs over a WireGuard tunnel because the car's cellular connection can't accept inbound connections.

```
 Xbox controller + Meta Quest ──► WireGuard VPS ◄── Cellular ◄── Raspberry Pi 5 on the car
         (operator)                  (relay)                      ├── master-api      :8000
                                                                  ├── video-api       :8001
                                                                  ├── controller-api  :8002
                                                                  └── mediamtx        :8889 (WebRTC)
```

## Documentation

Each part of the project has its own detailed README:

| Doc | Covers |
|:--|:--|
| [Physical Build](Physical_Build_Info/readme.md) | Parts list, wiring, power, assembly, safety |
| [System Setup](System_Setup_Info/readme.md) | Raspberry Pi OS, I2C, WireGuard, Docker, Solis Tag, and how the VPS connects everything |
| [Video Container](video-container/Readme.md) | Camera capture, FFmpeg, MediaMTX/WebRTC streaming, recording |
| [Master API](master-container/README.md) | Orchestration, state machine, driver lease, telemetry |
| [Project Proposal](CC_Proposal.pdf) | Original goals and milestones |

## Components

| Service | Folder | Port | What it does |
|:--|:--|:-:|:--|
| **master-api** | `master-container/` | 8000 | Central orchestrator. Routes commands, enforces the state machine, allows one driver at a time, logs telemetry. |
| **video-api** | `video-container/` | 8001 | Captures the webcam, encodes H.264, publishes to MediaMTX, and records video. |
| **camera-mediamtx** | `video-container/mediamtx.yml` | 8889 | Serves the live stream to the driver over WebRTC. |
| **controller-api** | `controller-container/` | 8002 | Drives the steering servo and ESC through the PCA9685 over I2C. |
| **Frontend** | `Frontend/` | — | Runs on the operator PC: Xbox controller relay, driver view on the Quest, spectator view. |

## Docker Deployment

All car-side services run on the Pi with Docker Compose. Setting up the Pi itself (OS, I2C, WireGuard, Docker) is covered in [System Setup](System_Setup_Info/readme.md).

### First deploy

```bash
git clone https://github.com/Nick-Pillsbury/CC.git ~/CC
cd ~/CC
docker compose -f docker-compose.yml -f master-container/compose.server.yaml up -d --build
```

`compose.server.yaml` adds the Master API's connection settings and its persistent history volume. Include it on every `up` so the Master API keeps them.

### Common commands

Run these from `~/CC` on the Pi. To include the Master API settings, set this alias first:

```bash
alias cc-compose='docker compose -f docker-compose.yml -f master-container/compose.server.yaml'
```

| Task | Command |
|:--|:--|
| Start / update everything | `cc-compose up -d --build` |
| Status of all services | `cc-compose ps` |
| Follow logs (all / one) | `cc-compose logs -f` / `cc-compose logs -f video-api` |
| Restart one service | `cc-compose restart controller-api` |
| Rebuild and redeploy one service | `cc-compose up -d --build master-api` |
| Shell inside a container | `cc-compose exec video-api sh` |
| Stop everything | `cc-compose down` |
| Pull latest code and redeploy | `git pull && cc-compose up -d --build` |
| Clean up old images | `docker image prune -f` |

### Health checks

```bash
curl http://localhost:8000/api/v1/health/live   # master-api
curl http://localhost:8001/status               # video-api
```

The Master API also has a scripted deploy that builds, tests, starts, and live-checks only the Master service, without requesting any movement:

```bash
python3 master-container/deploy.py
```

All services use `restart: unless-stopped`, so they come back up automatically after the Pi reboots.

## Tech Stack

- **Raspberry Pi 5** with Raspberry Pi OS, Python, and **FastAPI** for all services
- **FFmpeg** + **MediaMTX** (WebRTC) for low-latency video
- **PCA9685** over I2C for servo / ESC control
- **Docker Compose** for deployment
- **WireGuard** (PiVPN) over a **Solis Tag** cellular hotspot for networking
- **Xbox controller** relay and **Meta Quest** (HDMI passthrough) for the driver

## Team

| Name | Role | Email |
|:--|:--|:--|
| Nick Pillsbury | Lead | pillsn@rpi.edu |
| Mark Evans | Contributor | evansm2@rpi.edu |
| Keith Wilfert | Contributor | wilfek@rpi.edu |
