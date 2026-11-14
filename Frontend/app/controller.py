"""
Controls:
    Left stick X    steer
    Right trigger   forward
    Left trigger    reverse
    A               start stream
    B               stop stream
    X               neutral, hold to keep the car stopped
"""

import logging
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("controller")

CAR_API_URL = os.getenv("CAR_API_URL", "http://10.0.0.51:8002")
VIDEO_API_URL = os.getenv("VIDEO_API_URL", "http://10.0.0.51:8001")

MAX_STEER_DEG = 180
MAX_THROTTLE_US = int(os.getenv("MAX_THROTTLE_US", "350"))  # lower this to limit top speed
THROTTLE_STEP_US = 10  # throttle is rounded to this so tiny trigger jitter doesn't spam the API
POLL_HZ = 30


BUTTON_A = 0x1000
BUTTON_B = 0x2000
BUTTON_X = 0x4000

STICK_DEADZONE = 7849 / 32767
TRIGGER_THRESHOLD = 30 / 255


@dataclass(frozen=True)
class Pad:
    """Controller state, normalized."""

    steer: float = 0.0  # -1 full left .. 1 full right
    throttle: float = 0.0  # -1 full reverse .. 1 full forward
    buttons: int = 0
    connected: bool = True


@dataclass(frozen=True)
class Command:
    service: str  # "car" or "video"
    path: str
    params: dict = field(default_factory=dict)


NEUTRAL = Command("car", "/neutral")


def pad_from_xinput(buttons: int, left_trigger: int, right_trigger: int, thumb_lx: int) -> Pad:
    """Converts raw XInput values into a Pad, applying dead zones."""

    def scaled(value: float, deadzone: float) -> float:
        value = max(-1.0, min(1.0, value))
        if abs(value) < deadzone:
            return 0.0
        return (abs(value) - deadzone) / (1 - deadzone) * (1 if value > 0 else -1)

    steer = scaled(thumb_lx / 32767, STICK_DEADZONE)
    throttle = scaled(right_trigger / 255, TRIGGER_THRESHOLD) - scaled(left_trigger / 255, TRIGGER_THRESHOLD)
    return Pad(steer=steer, throttle=throttle, buttons=buttons)


class Relay:
    """Turns controller states into API commands, only sending what changed."""

    def __init__(self, max_throttle_us: int = MAX_THROTTLE_US):
        self.max_throttle_us = max_throttle_us
        self._buttons = 0
        self.reset()

    def reset(self) -> None:
        """Forget what was sent, so the next update resends the current steering and throttle."""
        self._steer = None
        self._motor = None

    def update(self, pad: Pad) -> list[Command]:
        if not pad.connected:
            self._buttons = 0
            if self._steer or self._motor:  # car was moving when the controller dropped
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
            if pressed & BUTTON_X:
                commands.append(NEUTRAL)
                self._steer = self._motor = 0
            return commands  # ignore sticks while e-stop is held

        steer = round(-pad.steer * MAX_STEER_DEG)
        if steer != self._steer:
            commands.append(Command("car", "/steer", {"deg": steer}))
            self._steer = steer

        motor = round(pad.throttle * self.max_throttle_us / THROTTLE_STEP_US) * THROTTLE_STEP_US
        if motor != self._motor:
            # forward with delta 0 is motor neutral without re-centering the steering
            path = "/backward" if motor < 0 else "/forward"
            commands.append(Command("car", path, {"delta": abs(motor)}))
            self._motor = motor

        return commands


class ApiClient:
    def __init__(self, car_url: str = CAR_API_URL, video_url: str = VIDEO_API_URL, timeout: float = 0.5):
        self._urls = {"car": car_url, "video": video_url}
        self._timeout = timeout

    def send(self, command: Command) -> None:
        url = self._urls[command.service] + command.path
        if command.params:
            url += "?" + urlencode(command.params)
        # The stream takes ~1 s to start, so give it longer.
        timeout = 5 if command.service == "video" else self._timeout
        with urlopen(Request(url, method="POST"), timeout=timeout):
            pass


def read_xinput(index: int = 0) -> Pad:
    """Reads controller index through the Windows XInput API."""
    import ctypes
    from ctypes import wintypes

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

    state = State()
    if _xinput().XInputGetState(index, ctypes.byref(state)) != 0:  # 0 = success
        return Pad(connected=False)
    g = state.pad
    return pad_from_xinput(g.buttons, g.left_trigger, g.right_trigger, g.thumb_lx)


_dll = None


def _xinput():
    global _dll
    if _dll is None:
        import ctypes

        for name in ("xinput1_4", "xinput9_1_0"):
            try:
                _dll = getattr(ctypes.windll, name)
                break
            except OSError:
                continue
        else:
            raise OSError("XInput not found. The controller relay only runs on Windows.")
    return _dll


def step(relay: Relay, client: ApiClient, pad: Pad) -> None:
    """Sends the commands for one controller reading."""
    for command in relay.update(pad):
        try:
            client.send(command)
            log.info("%s %s %s", command.service, command.path, command.params or "")
        except OSError as exc:
            log.warning("%s %s failed: %s", command.service, command.path, exc)
            relay.reset()  # retry steering/throttle on the next tick
            break


def run(client: ApiClient | None = None, read_pad=read_xinput) -> None:
    client = client or ApiClient()
    relay = Relay()
    connected = None
    log.info("Controller relay running. Car: %s  Video: %s", CAR_API_URL, VIDEO_API_URL)
    try:
        while True:
            pad = read_pad()
            if pad.connected != connected:
                connected = pad.connected
                log.info("Controller %s", "connected" if connected else "disconnected")
            step(relay, client, pad)
            time.sleep(1 / POLL_HZ)
    finally:
        try:
            client.send(NEUTRAL)  # never leave the car moving
        except OSError:
            log.warning("Could not send neutral on exit")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        run()
    except KeyboardInterrupt:
        pass
