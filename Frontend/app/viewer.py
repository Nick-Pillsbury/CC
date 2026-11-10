import os
import subprocess

STREAM_URL = os.getenv("STREAM_URL", "http://10.0.0.51:8889/stream")


def open_stream(url: str = STREAM_URL, kiosk: bool = False) -> subprocess.Popen:
    cmd = ["cmd", "/c", "start", url]
    return subprocess.Popen(cmd, shell=True)


if __name__ == "__main__":
    open_stream()

