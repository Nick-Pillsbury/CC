import ctypes
from ctypes import wintypes
import logging
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("controller")

CAR_API_URL = os.getenv("CAR_API_URL", "http://10.0.0.51:8002")

MAX_STEER_DEG = 180
MAX_THROTTLE_US = int(os.getenv("MAX_THROTTLE_US", "350"))
POLL_HZ = 30

STICK_DEADZONE = 7849 / 32767
TRIGGER_THRESHOLD = 30 / 255

_dll = None


def _xinput():
    global _dll
    if _dll is None:
        for name in ("xinput1_4", "xinput9_1_0"):
            try:
                _dll = getattr(ctypes.windll, name)
                break
            except OSError:
                continue
        else:
            raise OSError("XInput not found. Requires Windows.")
    return _dll


class Gamepad(ctypes.Structure):
    _fields_ = [
        ("buttons", wintypes.WORD),
        ("left_trigger", ctypes.c_ubyte),
        ("right_trigger", ctypes.c_ubyte),
        ("thumb_lx", wintypes.SHORT),
        ("thumb_ly", wintypes.SHORT),
        ("thumb_rx", wintypes.SHORT),
        ("thumb_ry", wintypes.SHORT),
    ]


class State(ctypes.Structure):
    _fields_ = [("packet", wintypes.DWORD), ("pad", Gamepad)]


def read_pad(index: int = 0):
    state = State()
    if _xinput().XInputGetState(index, ctypes.byref(state)) != 0:
        return None

    g = state.pad

    def scaled(val: float, deadzone: float) -> float:
        val = max(-1.0, min(1.0, val))
        if abs(val) < deadzone:
            return 0.0
        return (abs(val) - deadzone) / (1 - deadzone) * (1 if val > 0 else -1)

    steer = scaled(g.thumb_lx / 32767, STICK_DEADZONE)
    throttle = scaled(g.right_trigger / 255, TRIGGER_THRESHOLD) - scaled(g.left_trigger / 255, TRIGGER_THRESHOLD)
    return {"steer": steer, "throttle": throttle, "buttons": g.buttons}


def send_command(path: str, params: dict | None = None) -> None:
    url = CAR_API_URL + path
    if params:
        url += "?" + urlencode(params)
    with urlopen(Request(url, method="POST"), timeout=0.5):
        pass


def run() -> None:
    log.info("Controller running against %s", CAR_API_URL)
    last_steer = None
    last_motor = None
    try:
        while True:
            pad = read_pad()
            if pad is None:
                time.sleep(1 / POLL_HZ)
                continue

            steer = round(-pad["steer"] * MAX_STEER_DEG)
            if steer != last_steer:
                try:
                    send_command("/steer", {"deg": steer})
                    last_steer = steer
                except OSError as exc:
                    log.warning("Steer error: %s", exc)

            motor = round(pad["throttle"] * MAX_THROTTLE_US)
            if motor != last_motor:
                try:
                    path = "/backward" if motor < 0 else "/forward"
                    send_command(path, {"delta": abs(motor)})
                    last_motor = motor
                except OSError as exc:
                    log.warning("Drive error: %s", exc)

            time.sleep(1 / POLL_HZ)
    finally:
        try:
            send_command("/neutral")
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        run()
    except KeyboardInterrupt:
        pass
