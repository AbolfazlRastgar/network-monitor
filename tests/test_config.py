"""Tests for configuration loading and validation."""

import pytest
import tempfile
from pathlib import Path
from network_exporter.config import load_config, ExporterConfig, TargetConfig


def test_config_load_valid():
    """Test loading valid configuration."""
    config_yaml = """
ping_interval: 10
hosts:
  - 8.8.8.8
  - address: example.com
    ports: [80, 443]
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_yaml)
        f.flush()
        try:
            config = load_config(f.name)
            assert config.ping_interval == 10
            assert len(config.hosts) == 2
            assert config.hosts[0].address == '8.8.8.8'
            assert config.hosts[1].address == 'example.com'
            assert config.hosts[1].ports == [80, 443]
        finally:
            Path(f.name).unlink()


def test_config_invalid_ping_interval():
    """Test validation of ping_interval."""
    with pytest.raises(ValueError, match="ping_interval"):
        ExporterConfig(ping_interval=0)


def test_config_invalid_port():
    """Test validation of port numbers."""
    with pytest.raises(ValueError, match="Invalid port"):
        TargetConfig(address="example.com", ports=[99999])


def test_config_missing_hosts():
    """Test that missing hosts raises error."""
    config_yaml = "ping_interval: 10"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_yaml)
        f.flush()
        try:
            with pytest.raises(ValueError):
                load_config(f.name)
        finally:
            Path(f.name).unlink()
