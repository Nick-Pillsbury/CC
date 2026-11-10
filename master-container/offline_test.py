"""Test Master with simulated downstream services; no Pi hardware is used."""

import argparse
from pathlib import Path
import subprocess
import sys
import unittest


def docker_command(source: Path, image: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--pull", "never", "--network", "none",
        "--mount", f"type=bind,source={source},target=/checks,readonly",
        "--workdir", "/checks", "--entrypoint", "python",
        image, "offline_test.py",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", action="store_true",
                        help="Use an existing Docker image with networking disabled.")
    parser.add_argument("--image", default="master-api-image:latest",
                        help="Image containing Master's Python dependencies.")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    if args.docker:
        try:
            return subprocess.run(docker_command(source, args.image), check=False).returncode
        except OSError as exc:
            print(f"Cannot run Docker: {exc}", file=sys.stderr)
            return 1

    if not (source / "tests" / "__init__.py").is_file():
        print("Missing tests folder. Extract the complete deployment package.", file=sys.stderr)
        return 1
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
    except ImportError:
        print("Dependencies are missing. Use --docker after building the Master image, "
              "or install requirements.txt first.", file=sys.stderr)
        return 1

    print("OFFLINE TEST: simulated Controller and Video; no live car commands.", flush=True)
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(source / "tests"), top_level_dir=str(source),
    )
    if suite.countTestCases() == 0:
        print("No tests found.", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print(f"PASS: {result.testsRun} offline tests. Physical hardware is not verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
