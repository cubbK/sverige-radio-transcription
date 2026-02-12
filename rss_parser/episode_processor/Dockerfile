FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Python 3.11 + ffmpeg (needed by Whisper for audio decoding)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Pre-download the Whisper model at build time (~3 GB).
# This avoids a multi-GB download on every cold start.
ARG WHISPER_MODEL_SIZE=large-v3
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD exec gunicorn --bind :${PORT} --workers 1 --threads 1 --timeout 600 main:app
