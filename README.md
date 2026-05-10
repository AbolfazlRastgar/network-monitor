# Network Exporter

A network monitoring exporter for Prometheus. Checks host availability (ICMP ping) and TCP port reachability.

## Features

- ICMP ping checks (host availability)
- TCP port checks (service availability)  
- Prometheus-compatible metrics
- Handles 10,000+ targets efficiently
- YAML configuration
- Docker ready

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run
python -m network_exporter.main -c example-config.yaml

# Check metrics
curl http://localhost:9116/metrics
```

## Configuration

Edit `example-config.yaml`:

```yaml
ping_interval: 10
hosts:
  - 8.8.8.8
  - address: example.com
    ports: [80, 443]
  - address: redis.local
    ports: [6379]
```

## Prometheus

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'network-exporter'
    static_configs:
      - targets: ['localhost:9116']
    scrape_interval: 15s
```

## Docker

```bash
docker-compose up -d
# Exporter: http://localhost:9116/metrics
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000
```

## Metrics

```
net_ping_up{target="..."}              # 1=up, 0=down
net_ping_latency_ms{target="..."}      # Latency in ms
net_tcp_up{target="...",port="..."}    # 1=open, 0=closed
net_tcp_connect_ms{target="...",port="..."}  # Connection time
```

## Configuration Options

| Option                  | Default | Description                    |
| ----------------------- | ------- | ------------------------------ |
| `ping_interval`         | 5       | Seconds between checks         |
| `ping_timeout_ms`       | 1000    | ICMP timeout                   |
| `tcp_timeout_ms`        | 1500    | TCP timeout                    |
| `http_port`             | 9116    | Metrics port                   |
| `max_concurrent_checks` | 100     | Max concurrent TCP connections |
| `json_logging`          | true    | JSON format logs               |
| `debug`                 | false   | Verbose logging                |

See `example-config.yaml` for all options.

## Scaling

| Scale            | Config                                            |
| ---------------- | ------------------------------------------------- |
| <100 targets     | `ping_interval: 5`, default settings              |
| 100-1000 targets | `ping_interval: 15`, `max_concurrent_checks: 100` |
| 1000+ targets    | `ping_interval: 60`, `max_concurrent_checks: 500` |

For 10,000+ targets, run multiple exporters on different machines.

## Troubleshooting

**Check if exporter is running:**

```bash
curl http://localhost:9116/health
```

**Enable debug logging:**

```bash
python -m network_exporter.main -c config.yaml --debug
```

**Memory too high:**

- Reduce `max_concurrent_checks`
- Increase `ping_interval`

## Architecture

- **Asyncio**: Concurrent monitoring without threads
- **icmplib**: Cross-platform ICMP ping
- **prometheus-client**: Prometheus metrics
- **aiohttp**: Async HTTP server

See `ARCHITECTURE.md` for details.

# 
