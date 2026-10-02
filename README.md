# CC
The goal of CC is to design and implement a cellular-enabled RC car, modified to run off a Raspberry Pi, for remote driving from anywhere with cell coverage.

## Master API skeleton

The initial Master API exposes mock-backed endpoints for motion control, video
recording, telemetry, liveness, and readiness. The mock clients let the API and
frontend contracts be developed before the hardware and video containers are
available.

Install and run it with:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn master_api.main:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

Run the endpoint tests with:

```powershell
python -m unittest discover -s tests -v
```
