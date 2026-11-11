import os
import shutil
import subprocess
from pathlib import Path

STREAM_URL = os.getenv("STREAM_URL", "http://10.0.0.51:8889/stream")

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "msedge",
    "chrome",
]


def find_browser() -> str:
    if override := os.getenv("BROWSER_PATH"):
        return override
    for candidate in BROWSER_CANDIDATES:
        path = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if path:
            return path
    raise FileNotFoundError("Chromium browser not found.")


def open_stream(url: str = STREAM_URL, kiosk: bool = False) -> subprocess.Popen:
    browser = find_browser()
    if kiosk:
        cmd = [browser, "--kiosk", url]
    else:
        cmd = [browser, f"--app={url}", "--window-size=1280,720"]
    return subprocess.Popen(cmd)


if __name__ == "__main__":
    import sys

    open_stream(kiosk="--kiosk" in sys.argv)
