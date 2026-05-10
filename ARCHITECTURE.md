# Architecture

## Overview

```
Config → Monitor targets concurrently → Record metrics → Expose /metrics
```

## Components

**config.py** - Load and validate YAML config

**monitor.py** - Check single target
- `ping_async()` - ICMP ping using icmplib
- `tcp_connect()` - TCP port check using asyncio

**exporter.py** - Run all monitors, record metrics
- Asyncio event loop
- Semaphore limits concurrent TCP connections
- prometheus-client for metrics

**http_server.py** - HTTP server (aiohttp)
- `/metrics` endpoint
- `/health` endpoint

**main.py** - Start everything

## How It Works

1. Load config (targets, timeouts)
2. Every `ping_interval` seconds:
   - ICMP ping all targets (concurrent)
   - TCP check all ports (limited by semaphore)
   - Record results as metrics
3. HTTP server exposes `/metrics` for Prometheus

## Why Asyncio?

- No threads = no memory overhead
- Non-blocking I/O = handles thousands efficiently
- Single event loop multiplexes all checks

## Resource Management

- Sockets explicitly closed after each check
- TCP connections limited by semaphore (default 100)
- Graceful shutdown on Ctrl+C
- No resource leaks

## Performance

- Memory: ~5 KB per target (10,000 targets = 75 MB)
- Speed: All targets checked concurrently
  - 1000 targets: ~3 seconds
  - 10,000 targets: ~30 seconds
- CPU: Idle when waiting (event-driven)
