# Master API Roadmap Through December

This roadmap extends the initial FastAPI skeleton into a safe, integrated Master API by the end of December. Dates are planning targets and should be adjusted when hardware or video dependencies change, but each phase has a concrete result that can be demonstrated and tested.

## Current foundation

The repository now has:

- a FastAPI application factory and versioned `/api/v1` routes;
- typed motion, recording, telemetry, and health models;
- replaceable hardware and video client interfaces;
- in-memory mock clients for development without the other containers; and
- endpoint tests for normal input, invalid input, degraded readiness, and mock state changes.

The mocks intentionally do not claim that authentication, control leases, physical safety, real networking, or persistence are complete.

## October: complete the API foundation

### Week 1: skeleton and mock contracts

- Finish the control, video, telemetry, liveness, and readiness route skeletons.
- Validate normalized motion values with Pydantic models.
- Use dependency injection so tests can replace hardware and video clients.
- Add endpoint tests using deterministic mock services.
- Review the generated OpenAPI document with the frontend team.

Completion check: the API starts locally, `/docs` displays every skeleton endpoint, and the automated test suite passes without hardware or video containers.

### Week 2: real downstream HTTP clients

- Implement asynchronous HTTP clients for the hardware and video contracts.
- Configure container base URLs and connect/read/write timeouts through environment variables.
- Reuse application-scoped HTTP connections and close them during shutdown.
- Translate downstream timeouts, connection failures, and invalid responses into stable API errors.
- Add fake HTTP server tests for success, timeout, refused connection, and 500 responses.

Completion check: changing configuration switches between mock and HTTP clients, with no route-code changes.

### Week 3: system state machine

- Implement explicit `STARTING`, `READY`, `CONTROLLED`, `DEGRADED`, `EMERGENCY_STOP`, and `SHUTTING_DOWN` states.
- Define guarded transitions and prevent commands in illegal states.
- Keep recording as a separate sub-state rather than multiplying car states.
- Broadcast state changes to connected frontend clients.
- Unit-test every legal and illegal transition.

Completion check: tests prove that motion is accepted only in the documented state and that critical failures enter a safe state.

### Week 4: authentication and single-driver lease

- Add identity authentication and spectator/driver/admin roles.
- Implement atomic lease acquisition, heartbeat, expiration, release, and administrative revocation.
- Keep authentication tokens separate from short-lived control leases.
- Ensure concurrent acquisition requests produce exactly one winner.
- Prevent logs and conflict responses from leaking tokens or lease identifiers.

Completion check: many spectators can read telemetry while exactly one authenticated driver can send motion commands.

## November: integrate and harden the core behavior

### Week 1: safe command lifecycle

- Add monotonically increasing motion sequence numbers and reject duplicates or stale commands.
- Define command freshness limits and behavior for delayed packets.
- Neutralize motion when the lease expires, the driver disconnects, or the API shuts down.
- Coordinate an independent watchdog with the hardware container.
- Make emergency stop latched and test its authorization and reset guards.

Completion check: fault-injection tests show a neutral command or emergency state for every loss-of-control path.

### Week 2: live telemetry

- Finalize telemetry fields, units, source timestamps, and update rates with the frontend and hardware teams.
- Add a WebSocket telemetry endpoint while retaining an HTTP snapshot endpoint.
- Mark data stale when downstream updates stop.
- Handle slow or disconnected WebSocket clients without blocking command processing.
- Test multiple spectators and reconnect behavior.

Completion check: the frontend displays current and stale status correctly for multiple viewers.

### Week 3: recording workflow

- Finalize start, stop, status, and failure contracts with the video team.
- Make recording operations idempotent with request IDs.
- Reconcile Master API status after ambiguous video timeouts.
- Add recording metadata needed by the frontend.
- Test duplicate, delayed, and reordered recording requests.

Completion check: retries never create accidental duplicate recordings and state converges after failures.

### Week 4: integration environment

- Create Docker Compose configuration for Master API, hardware mock, and video mock services.
- Add container health checks and readiness-aware startup behavior.
- Test WireGuard addressing, container-to-container authentication, and allowed network exposure.
- Run end-to-end controller-to-mock-hardware and video-control scenarios.
- Document local setup and common troubleshooting steps.

Completion check: a new team member can start the integrated mock system and run the documented demo flow.

## December: verification, observability, and demo readiness

### Week 1: logs and metrics

- Add request/correlation IDs across the Master API and downstream calls.
- Produce structured event logs for leases, state transitions, rejected commands, recording changes, and failures.
- Redact identity tokens, lease secrets, and sensitive configuration.
- Add request counts, error counts, downstream timeout counts, and latency histograms.
- Create a basic dashboard or documented metric queries for system health.

Completion check: a failed demo sequence can be reconstructed from logs without exposing secrets.

### Week 2: performance and network testing

- Measure HTTP and WebSocket motion at 10, 20, and 30 updates per second.
- Record median, p95, p99, and maximum command latency under realistic cellular conditions.
- Test packet loss, jitter, reconnects, and temporary dependency outages.
- Tune command, heartbeat, lease, and watchdog intervals using measured results.
- Run a longer soak test for memory, connection, or task leaks.

Completion check: chosen timing values are supported by measurements and meet the team's safe stopping target.

### Week 3: security and safety review

- Verify authorization on every route and WebSocket connection.
- Confirm that clients cannot bypass the Master API to control hardware.
- Review CORS, secret management, token expiration, rate limits, and dependency versions.
- Re-run emergency-stop and lease-race tests against real containers.
- Document remaining risks and manual safety procedures.

Completion check: the team has a signed-off safety checklist and no known path for a spectator to drive the car.

### Week 4: final integration and presentation

- Connect the real hardware, video service, controller relay, and frontend.
- Run a repeatable pre-demo health and calibration checklist.
- Practice normal driving, recording, spectator mode, connection loss, and emergency-stop scenarios.
- Fix high-priority integration defects and freeze the API contract.
- Update README, OpenAPI examples, architecture diagrams, and final presentation material.

Completion check: the complete system can run the planned demonstration repeatedly and recover safely from rehearsed failures.

## Prioritized backlog

If dependencies arrive early, work in this order:

1. Safety and hardware watchdog integration.
2. Single-driver lease correctness and race testing.
3. Real hardware/video client contracts.
4. State machine and failure behavior.
5. Telemetry freshness and multi-spectator delivery.
6. Recording idempotency and recovery.
7. Observability and performance measurement.
8. Documentation and demo polish.

Optional work should begin only after the required path is stable. Possible stretch items include richer telemetry history, administrative session tools, recorded-video browsing, configurable speed modes, and frontend-generated client code from OpenAPI.

## Weekly evidence of progress

Each week should produce at least two of the following:

- an implemented and reviewed API behavior;
- automated tests for that behavior and its failure cases;
- an integration result with another container or the frontend;
- measured latency, reliability, or safety data;
- a resolved architecture decision; or
- updated setup, contract, or operations documentation.

This keeps the work through December focused on demonstrable system progress rather than adding endpoints without validated behavior.
