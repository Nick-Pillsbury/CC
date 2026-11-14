import os
import shutil
import subprocess
import tempfile
from pathlib import Path

STREAM_URL = os.getenv("STREAM_URL", "http://10.0.0.51:8889/stream")

# Edge ships with Windows, so it's tried first. BROWSER_PATH overrides the search.
BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "msedge",
    "chrome",
]

# A separate profile makes the browser open a fresh window that honors --kiosk/--app,
# even if the user already has the same browser open.
PROFILE_DIR = Path(tempfile.gettempdir()) / "cc-stream-viewer"


def find_browser() -> str:
    if override := os.getenv("BROWSER_PATH"):
        return override
    for candidate in BROWSER_CANDIDATES:
        path = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if path:
            return path
    raise FileNotFoundError("No Edge or Chrome found. Set BROWSER_PATH to a Chromium-based browser.")


def browser_command(browser: str, url: str, kiosk: bool = False, profile_dir: Path = PROFILE_DIR) -> list[str]:
    cmd = [
        browser,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--autoplay-policy=no-user-gesture-required",  # start video without a click
        "--ignore-certificate-errors",  # in case the stream uses a self-signed cert
    ]
    if kiosk:
        cmd += ["--kiosk", url]  # full screen, exit with Alt+F4
    else:
        cmd += [f"--app={url}", "--window-size=1280,720"]  # plain window, no tabs or address bar
    return cmd


def open_stream(url: str = STREAM_URL, kiosk: bool = False) -> subprocess.Popen:
    return subprocess.Popen(browser_command(find_browser(), url, kiosk))


if __name__ == "__main__":
    import sys

    open_stream(kiosk="--kiosk" in sys.argv)