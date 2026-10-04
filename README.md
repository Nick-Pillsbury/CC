# CC — Cellular-Controlled Car
 
A cellular-enabled RC car run by a Raspberry Pi, driven remotely from anywhere with cell coverage. The driver wears a Meta Quest (HDMI passthrough) and steers with an Xbox controller while watching the car's live camera feed.
 
## How It Works
 
The system has four modular parts:
 
| Component | What it does |
|---|---|
| **Hardware Control Container** | Controls the steering servo and drive motor. Handles motion smoothing, calibration, speed presets, and safety limits (e-stop, max steering angle, request rate limits). |
| **Video Capture & Streaming Container** | Captures the camera, streams it live over the internet, records video, and reports stream health. |
| **Master API** | Central orchestrator. Routes commands, enforces a state machine, allows only one driver at a time (session tokens), and logs telemetry. |
| **Frontend** | Quest display plus Xbox controller relay for the driver, and a spectator view for everyone else. Shows steering angle, speed, and recording status. |
 
## Tech Stack
 
- **Raspberry Pi** + Python (motor control, video capture/streaming)
- **FastAPI** (Master API)
- **Controller-relay script** (Xbox input → Master API)
- **Meta Quest** in HDMI passthrough (driver display)
- **Docker** for containers, **WireGuard** for networking
## Milestones
 
| When | Goal |
|---|---|
| Sept – early Oct | Pi, WireGuard, and Git repo setup; research tools; initial design docs |
| End of Oct | Basic wiring and test setup; servo/motor movement; static video stream; skeleton API; controller inputs hitting mock API |
| End of Nov | Core functionality: motor/servo control, live streaming and recording, state machine, single-user control, live status in frontend |
| End of Dec | All features finished and polished: safety limits, e-stop, session tokens, telemetry, spectator/driver modes, gamification |
| Presentation day | Working demo and final documentation |
 
## Team
 
| Name | Role | Email |
|---|---|---|
| Nick Pillsbury | Lead | pillsn@rpi.edu |
| Mark Evans | Contributor | evansm2@rpi.edu |
| Keith Wilfert | Contributor | wilfek@rpi.edu |
