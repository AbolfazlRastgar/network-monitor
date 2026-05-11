"""Async network monitoring: ICMP ping and TCP checks."""

import asyncio
import time
from typing import Optional, Tuple
from dataclasses import dataclass, field
import icmplib
from network_exporter.logger import get_logger

log = get_logger(__name__)


@dataclass
class CheckResult:
    """Result of a single check (ping or TCP)."""
    success: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class TargetMetrics:
    """Current metrics for a target."""
    address: str
    ping_result: CheckResult = field(default_factory=lambda: CheckResult(success=False))
    tcp_results: dict = field(default_factory=dict)  # port -> CheckResult


class TargetMonitor:
    """Async monitor for a single target (ICMP + TCP checks)."""

    def __init__(
        self,
        address: str,
        ports: list,
        ping_timeout_ms: int = 1000,
        tcp_timeout_ms: int = 1500,
        icmp_payload_size: int = 56,
        debug: bool = False,
    ):
        self.address = address
        self.ports = list(ports)  # Make copy
        self.ping_timeout_sec = ping_timeout_ms / 1000.0
        self.tcp_timeout_sec = tcp_timeout_ms / 1000.0
        self.icmp_payload_size = icmp_payload_size
        self.debug = debug

        self.metrics = TargetMetrics(address=address)
        # Initialize TCP results dict
        for port in self.ports:
            self.metrics.tcp_results[port] = CheckResult(success=False)

        self._last_check_time = 0.0

    async def ping_async(self) -> CheckResult:
        """Perform async ICMP ping using icmplib.

        icmplib offers non-blocking async probe; runs in thread pool if needed.
        Returns after first successful reply or timeout.

        Returns:
            CheckResult with success flag and latency_ms
        """
        try:
            # icmplib.async_ping handles the async ICMP probe.
            # count=1, timeout in seconds, payload_size
            host = await asyncio.to_thread(
                icmplib.ping,
                self.address,
                count=1,
                timeout=self.ping_timeout_sec,
                payload_size=self.icmp_payload_size,
            )

            if host.is_alive:
                latency = host.avg_rtt  # Average RTT in milliseconds
                if self.debug:
                    log.debug(
                        f"Ping {self.address}: up ({latency:.2f} ms)",
                        extra={"target": self.address},
                    )
                return CheckResult(success=True, latency_ms=latency)
            else:
                if self.debug:
                    log.debug(
                        f"Ping {self.address}: down (100% loss)",
                        extra={"target": self.address},
                    )
                return CheckResult(success=False)

        except icmplib.NameLookupError as e:
            if self.debug:
                log.debug(
                    f"Ping {self.address}: DNS error: {e}",
                    extra={"target": self.address},
                )
            return CheckResult(success=False, error="DNS resolution failed")
        except icmplib.ICMPLibError as e:
            if self.debug:
                log.debug(
                    f"Ping {self.address}: ICMP error: {e}",
                    extra={"target": self.address},
                )
            return CheckResult(success=False, error=str(type(e).__name__))
        except Exception as e:
            log.warning(
                f"Ping {self.address}: unexpected error: {type(e).__name__}: {e}",
                extra={"target": self.address},
            )
            return CheckResult(success=False, error=str(type(e).__name__))

    async def tcp_connect(self, port: int) -> CheckResult:
        """Perform async TCP connection check.

        Uses asyncio.open_connection for non-blocking socket I/O.
        Properly closes the connection to avoid resource leaks.

        Args:
            port: Target port

        Returns:
            CheckResult with success flag and latency_ms
        """
        start = time.time()
        try:
            # open_connection returns (reader, writer) or raises
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.address, port),
                timeout=self.tcp_timeout_sec,
            )
            latency_ms = (time.time() - start) * 1000.0

            # Properly close the connection to avoid socket leaks
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass  # Close best-effort

            if self.debug:
                log.debug(
                    f"TCP {self.address}:{port}: up ({latency_ms:.2f} ms)",
                    extra={"target": self.address, "port": port},
                )
            return CheckResult(success=True, latency_ms=latency_ms)

        except asyncio.TimeoutError:
            if self.debug:
                log.debug(
                    f"TCP {self.address}:{port}: timeout",
                    extra={"target": self.address, "port": port},
                )
            return CheckResult(success=False, error="timeout")
        except ConnectionRefusedError:
            if self.debug:
                log.debug(
                    f"TCP {self.address}:{port}: refused",
                    extra={"target": self.address, "port": port},
                )
            return CheckResult(success=False, error="refused")
        except OSError as e:
            if self.debug:
                log.debug(
                    f"TCP {self.address}:{port}: OS error: {e}",
                    extra={"target": self.address, "port": port},
                )
            return CheckResult(success=False, error=str(type(e).__name__))
        except Exception as e:
            log.warning(
                f"TCP {self.address}:{port}: unexpected error: {type(e).__name__}: {e}",
                extra={"target": self.address, "port": port},
            )
            return CheckResult(success=False, error=str(type(e).__name__))

    async def check(self) -> None:
        """Run ping and all TCP checks concurrently.

        Updates self.metrics with results.
        """
        try:
            # Run ping and TCP checks concurrently
            ping_task = self.ping_async()
            tcp_tasks = {port: self.tcp_connect(port) for port in self.ports}

            # Gather all results
            ping_result = await ping_task
            tcp_results = {}
            for port, task in tcp_tasks.items():
                tcp_results[port] = await task

            # Update metrics atomically
            self.metrics.ping_result = ping_result
            for port, result in tcp_results.items():
                self.metrics.tcp_results[port] = result

            self._last_check_time = time.time()

        except Exception as e:
            log.error(
                f"Unexpected error during check for {self.address}: {e}",
                extra={"target": self.address},
            )
            # Keep previous metrics on error
            self.metrics.ping_result = CheckResult(
                success=False, error="check failed"
            )
            for port in self.ports:
                self.metrics.tcp_results[port] = CheckResult(
                    success=False, error="check failed"
                )

    def get_metrics(self) -> TargetMetrics:
        """Get current metrics snapshot."""
        return self.metrics
