"""Service configuration, read from environment variables."""
import os
from pydantic import BaseModel, ConfigDict, Field

# Maps each setting to the environment variable that overrides it.
_ENV_VARS = {
    "camera_device": "CAMERA_DEVICE",
    "video_size": "VIDEO_SIZE",
    "framerate": "FRAMERATE",
    "bitrate": "BITRATE",
    "bufsize": "BUFSIZE",
    "rtsp_port": "RTSP_PORT",
}

class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_device: str = "/dev/video0"
    video_size: str = Field("1920x1080", pattern=r"^\d+x\d+$")
    framerate: int = Field(30, gt=0)
    bitrate: str = "3M"
    bufsize: str = "1500k"
    rtsp_port: int = Field(8554, gt=0, lt=65536)

    @property
    def rtsp_url(self) -> str:
        return f"rtsp://127.0.0.1:{self.rtsp_port}/stream"

    @classmethod
    def from_env(cls) -> "Settings":
        values = {field: os.environ[var] for field, var in _ENV_VARS.items() if var in os.environ}
        return cls(**values)
