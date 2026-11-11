import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import logging
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("controller")

CAR_API_URL = os.getenv("CAR_API_URL", "http://10.0.0.51:8002")
VIDEO_API_URL = os.getenv("VIDEO_API_URL", "http://10.0.0.51:8001")

MAX_STEER_DEG = 180
MAX_THROTTLE_US = int(os.getenv("MAX_THROTTLE_US", "350"))
THROTTLE_STEP_US = 10
POLL_HZ = 30

BUTTON_A = 0x1000
BUTTON_B = 0x2000
BUTTON_X = 0x4000

STICK_DEADZONE = 7849 / 32767
TRIGGER_THRESHOLD = 30 / 255


@dataclass(frozen=True)
class Pad:
    steer: float = 0.0
    throttle: float = 0.0
    buttons: int = 0
    connected: bool = True


@dataclass(frozen=True)
class Command:
    service: str
    path: str
    params: dict = field(default_factory=dict)


NEUTRAL = Command("car", "/neutral")


def pad_from_xinput(buttons: int, left_trigger: int, right_trigger: int, thumb_lx: int) -> Pad:
    def scaled(value: float, deadzone: float) -> float:
        value = max(-1.0, min(1.0, value))
        if abs(value) < deadzone:
            return 0.0
        return (abs(value) - deadzone) / (1 - deadzone) * (1 if value > 0 else -1)

    steer = scaled(thumb_lx / 32767, STICK_DEADZONE)
    throttle = scaled(right_trigger / 255, TRIGGER_THRESHOLD) - scaled(left_trigger / 255, TRIGGER_THRESHOLD)
    return Pad(steer=steer, throttle=throttle, buttons=buttons)


class Relay:
    def __init__(self, max_throttle_us: int = MAX_THROTTLE_US):
        self.max_throttle_us = max_throttle_us
        self._buttons = 0
        self._steer = None
        self._motor = None

    def reset(self) -> None:
        self._steer = None
        self._motor = None

    def update(self, pad: Pad) -> list[Command]:
        if not pad.connected:
            self._buttons = 0
            if self._steer or self._motor:
                self._steer = self._motor = 0
                return [NEUTRAL]
            return []

        pressed = pad.buttons & ~self._buttons
        self._buttons = pad.buttons
        commands = []

        if pressed & BUTTON_A:
            commands.append(Command("video", "/stream/start"))
        if pressed & BUTTON_B:
            commands.append(Command("video", "/stream/stop"))

        if pad.buttons & BUTTON_X:
            commands.append(NEUTRAL)
            self._steer = self._motor = 0
            return commands

        steer = round(-pad.steer * MAX_STEER_DEG)
        if steer != self._steer:
            commands.append(Command("car", "/steer", {"deg": steer}))
            self._steer = steer

        motor = round(pad.throttle * self.max_throttle_us / THROTTLE_STEP_US) * THROTTLE_STEP_US
        if motor != self._motor:
            path = "/backward" if motor < 0 else "/forward"
            commands.append(Command("car", path, {"delta": abs(motor)}))
            self._motor = motor

        return commands


def send_command(command: Command) -> None:
    base = VIDEO_API_URL if command.service == "video" else CAR_API_URL
    url = base + command.path
    if command.params:
        url += "?" + urlencode(command.params)
    timeout = 5 if command.service == "video" else 0.5
    with urlopen(Request(url, method="POST"), timeout=timeout):
        pass


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
            raise OSError("XInput not found.")
    return _dll


def read_xinput(index: int = 0) -> Pad:
    state = State()
    if _xinput().XInputGetState(index, ctypes.byref(state)) != 0:
        return Pad(connected=False)
    g = state.pad
    return pad_from_xinput(g.buttons, g.left_trigger, g.right_trigger, g.thumb_lx)


def run() -> None:
    relay = Relay()
    log.info("Controller running. Car: %s  Video: %s", CAR_API_URL, VIDEO_API_URL)
    try:
        while True:
            pad = read_xinput()
            for command in relay.update(pad):
                try:
                    send_command(command)
                except OSError as exc:
                    log.warning("Command failed: %s", exc)
                    relay.reset()
                    break
            time.sleep(1 / POLL_HZ)
    finally:
        try:
            send_command(NEUTRAL)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        run()
    except KeyboardInterrupt:
        pass
