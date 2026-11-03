FROM python:3.11-slim

# Install system-level build tools and I2C development libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    i2c-tools \
    libi2c-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app   

# Install Python dependencies
COPY reqs.txt .
RUN pip install --no-cache-dir -r reqs.txt
RUN pip install --upgrade adafruit-blinka adafruit-platformdetect

# Copy backend movement and API modules
COPY movement.py main.py ./

EXPOSE 8002

# Start Uvicorn bound to all interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]