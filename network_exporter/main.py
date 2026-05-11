"""Entry point for network exporter."""

import asyncio
import argparse
import signal
import sys
from pathlib import Path

from network_exporter.config import load_config
from network_exporter.monitor import TargetMonitor
from network_exporter.exporter import Exporter
from network_exporter.http_server import MetricsServer
from network_exporter.logger import setup_logging, get_logger

log = get_logger(__name__)


class ExporterApp:
    """Main application orchestrator."""

    def __init__(
        self,
        config_path: str,
        json_logging: bool = True,
        debug: bool = False,
    ):
        self.config = load_config(config_path)
        self.debug = debug or self.config.debug
        self.json_logging = json_logging and self.config.json_logging

        # Setup logging
        setup_logging(debug=self.debug, json_format=self.json_logging)

        # Create monitors from config
        self.monitors = [
            TargetMonitor(
                address=target.address,
                ports=target.ports,
                ping_timeout_ms=self.config.ping_timeout_ms,
                tcp_timeout_ms=self.config.tcp_timeout_ms,
                icmp_payload_size=self.config.icmp_payload_size,
                debug=self.debug,
            )
            for target in self.config.hosts
        ]

        # Create exporter
        self.exporter = Exporter(
            monitors=self.monitors,
            check_interval=self.config.ping_interval,
            max_concurrent_checks=self.config.max_concurrent_checks,
            debug=self.debug,
        )

        # Create HTTP server
        self.server = MetricsServer(
            get_metrics_fn=self.exporter.get_metrics,
            host=self.config.http_bind_addr,
            port=self.config.http_port,
        )

        self._loop = None
        self._exporter_task = None

    async def start(self) -> None:
        """Start the application."""
        log.info(
            f"Network Exporter starting: "
            f"{len(self.monitors)} targets, "
            f"interval={self.config.ping_interval}s, "
            f"http={self.config.http_bind_addr}:{self.config.http_port}"
        )

        # Start exporter
        self._exporter_task = self.exporter.start()

        # Start HTTP server
        await self.server.start()

        log.info("Network Exporter started successfully")

    async def shutdown(self) -> None:
        """Gracefully shutdown the application."""
        log.info("Shutting down Network Exporter...")

        try:
            # Shutdown exporter
            await self.exporter.shutdown()

            # Shutdown HTTP server
            await self.server.shutdown()

            # Cancel exporter task if still running
            if self._exporter_task and not self._exporter_task.done():
                self._exporter_task.cancel()
                try:
                    await self._exporter_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            log.error(f"Error during shutdown: {e}")
        finally:
            log.info("Network Exporter shutdown complete")

    async def run_forever(self) -> None:
        """Run the application until interrupted."""
        await self.start()

        try:
            # Wait forever
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Async network monitoring exporter for Prometheus"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--no-json-logging",
        action="store_true",
        help="Disable structured JSON logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Validate config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    try:
        app = ExporterApp(
            config_path=str(config_path),
            json_logging=not args.no_json_logging,
            debug=args.debug,
        )
    except Exception as e:
        print(f"Error: Failed to initialize application: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(sig, frame):
        log.info(f"Received signal {sig}, initiating shutdown...")
        # Cancel the main task
        if task:
            task.cancel()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Run the app
    try:
        task = loop.create_task(app.run_forever())
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        loop.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
