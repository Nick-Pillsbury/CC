# Video recording contract for Master

The existing Video service has no recording endpoints. This is the small
downstream contract required by Master's recording routes; it is not a claim
that the Video implementation exists.

| Video endpoint | Behavior |
| --- | --- |
| `GET /recordings/current` | Return the active recording, otherwise the most recent one or `idle`. |
| `POST /recordings` | Accept `{"request_id":"UUID"}`. Use that UUID as the recording ID. |
| `DELETE /recordings/{recording_id}` | Stop only that recording. |

All successful responses use this shape (optional fields may be null):

```json
{
  "state": "recording",
  "recording_id": "f0f9fa66-053c-4c06-8e7e-ac9ee8d990df",
  "started_at": "2026-11-17T22:00:00Z",
  "stopped_at": null,
  "detail": null
}
```

States are `idle`, `recording`, `stopped`, and `failed`. Master additionally uses
`unsupported` and `unavailable` for capability and connection reporting.

Video must persist recording IDs and metadata alongside the saved media:

- Repeating a start ID returns its existing result, even after it was stopped.
- A new ID while another recording is active returns 409.
- Repeating a stop returns `stopped` without affecting newer recordings.
- An unknown stop ID returns 409. Reserve 404/405/501 for unsupported operations.
- Successful starts return `recording` (or the already completed `stopped` result).
- Successful stops return `stopped`. Return an error if the file cannot be finalized.
- The ID in every successful mutation response must match the requested ID.

Master uses an eight-second read deadline for mutations and checks status once
after a timeout. It never automatically replays a start/stop. If the result is
still uncertain, it returns the timeout so the caller can check status and retry
the same ID. Recording must preserve the live stream and save to persistent
storage; those responsibilities remain with Video.
