FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 app && mkdir -p /data/downloads && chown -R app:app /data
USER app
ENV OUTPUT_DIR=/data/downloads HOST=127.0.0.1 PORT=8081
CMD ["web-audio-extract-server"]
