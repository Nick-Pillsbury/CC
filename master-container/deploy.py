"""Build, test, and deploy only Master using the Pi's existing Compose stack."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from offline_test import docker_command


LIVE_CHECK = """
import json
import sys
from urllib.error import HTTPError
from urllib.request import urlopen

for path in ('/ping', '/api/v1/health/ready', '/api/v1/telemetry'):
    print(path, flush=True)
    try:
        with urlopen('http://127.0.0.1:8000' + path, timeout=10) as response:
            body = json.load(response)
    except HTTPError as exc:
        print(exc.read().decode(errors='replace'))
        sys.exit(1)
    print(json.dumps(body, indent=2), flush=True)
    if path.endswith('/ready') and not body.get('ready'):
        sys.exit(1)
"""


def find_compose(project: Path) -> Path:
    candidates = [project / name for name in (
        "compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml",
    ) if (project / name).is_file()]
    if len(candidates) != 1:
        raise ValueError("Cannot choose a Compose file. Pass --compose /path/to/docker-compose.yml.")
    return candidates[0]


def deploy(source: Path, compose_file: Path) -> None:
    if not compose_file.is_file():
        raise ValueError(f"Compose file does not exist: {compose_file}")
    override = source / "compose.server.yaml"
    if not override.is_file():
        raise ValueError(f"Master override is missing: {override}")
    compose = ["docker", "compose", "-f", str(compose_file), "-f", str(override)]
    configuration = subprocess.run(
        compose + ["config", "--format", "json"], check=True, capture_output=True, text=True,
    )
    service = json.loads(configuration.stdout).get("services", {}).get("master-api", {})
    image = service.get("image")
    build = service.get("build", {})
    context = build.get("context") if isinstance(build, dict) else build
    if not image or not context:
        raise ValueError("The master-api service must define both image and build in Compose.")
    if Path(context).resolve() != source:
        raise ValueError(f"Master build context is {context}, but uploaded files are in {source}. "
                         "Set master-api.build to this master-container folder before deploying.")

    print("Building Master only...", flush=True)
    subprocess.run(compose + ["build", "master-api"], check=True)
    print("Testing uploaded Master code in an isolated container...", flush=True)
    subprocess.run(docker_command(source, image), check=True)
    print("Starting Master with its Controller and Video connection settings...", flush=True)
    subprocess.run(compose + [
        "up", "-d", "--no-deps", "--wait", "--wait-timeout", "60", "master-api",
    ], check=True)
    print("Checking the running API and both downstream services...", flush=True)
    try:
        subprocess.run(compose + [
            "exec", "-T", "master-api", "python", "-c", LIVE_CHECK,
        ], check=True)
    except subprocess.CalledProcessError:
        print("Master was deployed, but a live check failed. Check the component details above. "
              "Controller and Video must already be running.", file=sys.stderr)
        raise
    print("PASS: Master deployed; health and telemetry checks passed. No movement was requested.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, help="Compose file; defaults to the parent folder.")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    try:
        compose_file = args.compose.resolve() if args.compose else find_compose(source.parent)
        deploy(source, compose_file)
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        print(f"Deployment stopped: command exited with status {exc.returncode}.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Deployment stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
