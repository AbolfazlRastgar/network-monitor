"""Async HTTP server for Prometheus metrics endpoint."""

from aiohttp import web
import asyncio
from typing import Callable
from network_exporter.logger import get_logger

log = get_logger(__name__)


class MetricsServer:
    """Simple aiohttp-based HTTP server for /metrics endpoint."""

    def __init__(
        self,
        get_metrics_fn: Callable[[], bytes],
        host: str = "0.0.0.0",
        port: int = 9116,
    ):
        """Initialize metrics server.

        Args:
            get_metrics_fn: Callable that returns metrics as bytes
            host: Bind address
            port: Listen port
        """
        self.host = host
        self.port = port
        self.get_metrics_fn = get_metrics_fn
        self.app = web.Application()
        self.app.router.add_get("/metrics", self._handle_metrics)
        self.app.router.add_get("/health", self._handle_health)
        self.runner = None

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handle GET /metrics request."""
        try:
            data = self.get_metrics_fn()
            return web.Response(
                body=data,
                content_type="text/plain; version=0.0.4; charset=utf-8",
            )
        except Exception as e:
            log.error(f"Error generating metrics: {e}")
            return web.Response(
                status=500, text=f"Error: {e}\n", content_type="text/plain"
            )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Simple health check endpoint."""
        return web.Response(status=200, text="OK\n", content_type="text/plain")

    async def start(self) -> None:
        """Start the HTTP server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        log.info(f"Metrics server listening on {self.host}:{self.port}/metrics")

    async def shutdown(self) -> None:
        """Gracefully shutdown the HTTP server."""
        if self.runner:
            await self.runner.cleanup()
        log.info("Metrics server shutdown")
