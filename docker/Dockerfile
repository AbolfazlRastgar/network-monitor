# Multi-stage build for minimal runtime image

# Build stage
FROM python:3.11-slim as builder

WORKDIR /build

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for ICMP (required by icmplib for raw sockets)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY network_exporter/ ./network_exporter/
COPY example-config.yaml ./config.yaml

# Set PATH for user-installed packages
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root user for security
RUN useradd -m -u 1000 exporter
USER exporter

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9116/health').read()"

# Expose metrics port
EXPOSE 9116

# Run exporter
CMD ["python", "-m", "network_exporter.main", "-c", "/app/config.yaml"]
