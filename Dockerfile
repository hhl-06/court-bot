# ── Court Bot Docker Image ──────────────────────────────
# Build:
#   docker build -t court-bot .
#
# Run (with config mounted):
#   docker run -v $(pwd)/config:/app/config court-bot run
#
# Run (interactive config wizard):
#   docker run -it court-bot init-config

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Court Bot"
LABEL org.opencontainers.image.description="Automated sports court booking bot"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install system deps (for potential Selenium/Chromium usage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install Python dependencies
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir ddddocr || true

# Create volume mount points
RUN mkdir -p /app/config /app/logs
VOLUME ["/app/config", "/app/logs"]

# Default command
ENTRYPOINT ["court-bot"]
CMD ["run"]
