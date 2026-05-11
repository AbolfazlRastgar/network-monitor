"""Configuration loading and validation."""

import yaml
from pathlib import Path
from typing import Any, Dict, List
from dataclasses import dataclass, field


@dataclass
class TargetConfig:
    """Single target configuration."""
    address: str
    ports: List[int] = field(default_factory=list)

    def __post_init__(self):
        if not self.address or not isinstance(self.address, str):
            raise ValueError(f"Invalid address: {self.address}")
        if not isinstance(self.ports, list):
            raise ValueError(f"Ports must be list, got {type(self.ports)}")
        for port in self.ports:
            if not isinstance(port, int) or port < 1 or port > 65535:
                raise ValueError(f"Invalid port {port} for {self.address}")


@dataclass
class ExporterConfig:
    """Main exporter configuration."""
    ping_interval: int = 5  # seconds between scan cycles
    ping_timeout_ms: int = 1000  # ICMP timeout per probe
    tcp_timeout_ms: int = 1500  # TCP connect timeout
    http_port: int = 9116  # Prometheus metrics port
    http_bind_addr: str = "0.0.0.0"  # HTTP listen address
    max_concurrent_checks: int = 100  # simultaneous TCP connections
    icmp_payload_size: int = 56  # ICMP payload (default ping)
    hosts: List[TargetConfig] = field(default_factory=list)
    json_logging: bool = True
    debug: bool = False

    def __post_init__(self):
        if self.ping_interval < 1:
            raise ValueError(f"ping_interval must be >= 1, got {self.ping_interval}")
        if self.ping_timeout_ms < 100 or self.ping_timeout_ms > 60000:
            raise ValueError(f"ping_timeout_ms out of range: {self.ping_timeout_ms}")
        if self.tcp_timeout_ms < 100 or self.tcp_timeout_ms > 60000:
            raise ValueError(f"tcp_timeout_ms out of range: {self.tcp_timeout_ms}")
        if self.http_port < 1024 or self.http_port > 65535:
            raise ValueError(f"Invalid http_port: {self.http_port}")
        if self.max_concurrent_checks < 1 or self.max_concurrent_checks > 1000:
            raise ValueError(f"max_concurrent_checks out of range: {self.max_concurrent_checks}")


def load_config(path: str) -> ExporterConfig:
    """Load and validate configuration from YAML file.

    Args:
        path: Path to YAML config file

    Returns:
        Validated ExporterConfig object

    Raises:
        FileNotFoundError: Config file not found
        ValueError: Invalid configuration
        yaml.YAMLError: YAML parse error
    """
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse config YAML: {e}")

    if not isinstance(data, dict):
        raise ValueError("Config root must be a dictionary")

    # Parse hosts
    hosts_data = data.get("hosts", [])
    if not isinstance(hosts_data, list):
        raise ValueError("'hosts' must be a list")

    targets = []
    for i, entry in enumerate(hosts_data):
        try:
            if isinstance(entry, str):
                targets.append(TargetConfig(address=entry, ports=[]))
            elif isinstance(entry, dict):
                address = entry.get("address")
                ports = entry.get("ports", [])
                targets.append(TargetConfig(address=address, ports=ports))
            else:
                raise ValueError(f"Invalid host entry type: {type(entry)}")
        except Exception as e:
            raise ValueError(f"Host entry {i}: {e}")

    # Create main config
    try:
        config = ExporterConfig(
            ping_interval=data.get("ping_interval", 5),
            ping_timeout_ms=data.get("ping_timeout_ms", 1000),
            tcp_timeout_ms=data.get("tcp_timeout_ms", 1500),
            http_port=data.get("http_port", 9116),
            http_bind_addr=data.get("http_bind_addr", "0.0.0.0"),
            max_concurrent_checks=data.get("max_concurrent_checks", 100),
            icmp_payload_size=data.get("icmp_payload_size", 56),
            json_logging=data.get("json_logging", True),
            debug=data.get("debug", False),
            hosts=targets,
        )
    except ValueError as e:
        raise ValueError(f"Config validation failed: {e}")

    return config
