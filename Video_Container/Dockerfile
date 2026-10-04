FROM python:3.14.3-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install ffmpeg and v4l2 tools (v4l-utils is for debugging the camera, e.g. v4l2-ctl --list-formats-ext)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg v4l-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so Docker caches this layer when only main.py changes
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Recordings dir inside the container (link it to /mnt/usb on the host for persistent storage)
RUN mkdir -p /recordings

# Defaults for main.py (override in docker-compose or with docker run -e)
ENV CAMERA_DEVICE=/dev/video0 \
    CAMERA_INPUT_FORMAT=mjpeg \
    VIDEO_SIZE=1280x720 \
    FRAMERATE=30 \
    BITRATE=2M \
    BUFSIZE=1M \
    RTSP_PORT=8554 \
    RECORDINGS_DIR=/recordings

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]