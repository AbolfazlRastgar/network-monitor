"""Prometheus exporter and scrape scheduling."""

import asyncio
import time
from typing import List, Dict
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

from network_exporter.monitor import TargetMonitor
from network_exporter.logger import get_logger

log = get_logger(__name__)


class Exporter:
    """Runs monitoring checks on interval and exposes Prometheus metrics.

    Architecture:
    - One asyncio task per target, running checks concurrently within the check window
    - Semaphore limits concurrent TCP connections to avoid resource exhaustion
    - Streaming metrics output (no bulk string concatenation)
    - Proper resource cleanup on shutdown
    """

    def __init__(
        self,
        monitors: List[TargetMonitor],
        check_interval: int,
        max_concurrent_checks: int = 100,
        debug: bool = False,
    ):
        self.monitors = monitors
        self.check_interval = check_interval
        self.max_concurrent_checks = max_concurrent_checks
        self.debug = debug

        # Semaphore to limit concurrent TCP connections
        self.tcp_semaphore = asyncio.Semaphore(max_concurrent_checks)

        # Prometheus metrics
        self.registry = CollectorRegistry()

        # Counter for total checks performed
        self.checks_total = Counter(
            "exporter_checks_total",
            "Total checks performed",
            ["target", "check_type"],
            registry=self.registry,
        )

        # Counter for check failures
        self.check_failures = Counter(
            "exporter_check_failures_total",
            "Total check failures",
            ["target", "check_type", "reason"],
            registry=self.registry,
        )

        # Gauge for ping status (1=up, 0=down)
        self.ping_up = Gauge(
            "net_ping_up",
            "Host responded to ping (1=up, 0=down)",
            ["target"],
            registry=self.registry,
        )

        # Histogram for ping latency
        self.ping_latency = Histogram(
            "net_ping_latency_ms",
            "Ping round-trip latency in milliseconds",
            ["target"],
            buckets=(10, 25, 50, 100, 250, 500, 1000),
            registry=self.registry,
        )

        # Gauge for TCP port status (1=up, 0=down)
        self.tcp_up = Gauge(
            "net_tcp_up",
            "TCP port reachable (1=up, 0=down)",
            ["target", "port"],
            registry=self.registry,
        )

        # Histogram for TCP connect latency
        self.tcp_latency = Histogram(
            "net_tcp_connect_ms",
            "TCP connection latency in milliseconds",
            ["target", "port"],
            buckets=(5, 10, 25, 50, 100, 250, 500, 1000),
            registry=self.registry,
        )

        self._running = False
        self._task = None

    async def run(self) -> None:
        """Main loop: run checks at regular interval.

        Runs all target checks concurrently within each check window.
        """
        self._running = True
        log.info(
            f"Starting exporter with {len(self.monitors)} targets, "
            f"interval={self.check_interval}s, concurrency={self.max_concurrent_checks}"
        )

        try:
            while self._running:
                cycle_start = time.time()

                # Run all checks concurrently
                await self._run_cycle()

                # Sleep remainder of interval (allow early wakeup for shutdown)
                elapsed = time.time() - cycle_start
                to_sleep = max(0.0, self.check_interval - elapsed)

                if self.debug:
                    log.debug(
                        f"Cycle completed in {elapsed:.2f}s, "
                        f"sleeping {to_sleep:.2f}s"
                    )

                # Sleep in small chunks to allow graceful shutdown
                while to_sleep > 0 and self._running:
                    await asyncio.sleep(min(0.5, to_sleep))
                    to_sleep -= 0.5

        except asyncio.CancelledError:
            log.info("Exporter run cancelled")
            self._running = False
        except Exception as e:
            log.error(f"Exporter loop error: {e}")
            self._running = False
            raise

    async def _run_cycle(self) -> None:
        """Execute all checks for this cycle."""
        tasks = [self._check_target(m) for m in self.monitors]

        # Run all checks concurrently, don't fail on individual errors
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                monitor = self.monitors[i]
                log.error(
                    f"Unhandled error during check for {monitor.address}: {result}",
                    extra={"target": monitor.address},
                )

    async def _check_target(self, monitor: TargetMonitor) -> None:
        """Run check for a single target with semaphore control."""
        async with self.tcp_semaphore:
            try:
                await monitor.check()
                self._record_metrics(monitor)
            except Exception as e:
                log.error(
                    f"Error checking {monitor.address}: {e}",
                    extra={"target": monitor.address},
                )

    def _record_metrics(self, monitor: TargetMonitor) -> None:
        """Record metrics for a target based on latest check results."""
        metrics = monitor.get_metrics()

        # Ping metrics
        ping_status = 1 if metrics.ping_result.success else 0
        self.ping_up.labels(target=monitor.address).set(ping_status)
        self.checks_total.labels(
            target=monitor.address, check_type="ping"
        ).inc()

        if not metrics.ping_result.success:
            reason = metrics.ping_result.error or "unknown"
            self.check_failures.labels(
                target=monitor.address, check_type="ping", reason=reason
            ).inc()
        elif metrics.ping_result.latency_ms is not None:
            self.ping_latency.labels(target=monitor.address).observe(
                metrics.ping_result.latency_ms
            )

        # TCP metrics
        for port, result in metrics.tcp_results.items():
            tcp_status = 1 if result.success else 0
            self.tcp_up.labels(target=monitor.address, port=port).set(tcp_status)
            self.checks_total.labels(
                target=monitor.address, check_type=f"tcp_{port}"
            ).inc()

            if not result.success:
                reason = result.error or "unknown"
                self.check_failures.labels(
                    target=monitor.address, check_type=f"tcp_{port}", reason=reason
                ).inc()
            elif result.latency_ms is not None:
                self.tcp_latency.labels(
                    target=monitor.address, port=port
                ).observe(result.latency_ms)

    def get_metrics(self) -> bytes:
        """Generate Prometheus text exposition format.

        Returns:
            Metrics as bytes in Prometheus format (version 0.0.4)
        """
        return generate_latest(self.registry)

    async def shutdown(self) -> None:
        """Gracefully shutdown the exporter."""
        log.info("Shutting down exporter...")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        log.info("Exporter shutdown complete")

    def start(self) -> asyncio.Task:
        """Start the exporter in background.

        Returns:
            asyncio.Task that can be awaited or cancelled
        """
        self._task = asyncio.create_task(self.run())
        return self._task
