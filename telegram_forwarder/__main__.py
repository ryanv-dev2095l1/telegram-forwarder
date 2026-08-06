import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from telegram_forwarder.config import load_config
from telegram_forwarder.forwarder import run_bot
from telegram_forwarder.metrics import start_metrics_server

logger = logging.getLogger("telegram_forwarder")


def parse_args():
    p = argparse.ArgumentParser(description="Telegram noise filter and fanout daemon")
    p.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="path to yaml config file",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("--test-rules", action="store_true", help="validate config rules syntax and exit")
    return p.parse_args()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # telethon and httpx get chatty
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    args = parse_args()
    setup_logging(args.verbose)

    if not args.config.exists():
        logger.error("config file not found: %s", args.config)
        sys.exit(1)

    try:
        cfg = load_config(args.config)
    except Exception as e:
        logger.error("failed parsing config: %s", e, exc_info=args.verbose)
        sys.exit(1)

    if args.test_rules:
        logger.info("loaded %d routes successfully", len(cfg.routes))
        sys.exit(0)

    if cfg.metrics.enabled:
        start_metrics_server(cfg.metrics.host, cfg.metrics.port)
        logger.info("metrics export on %s:%d", cfg.metrics.host, cfg.metrics.port)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop_event = asyncio.Event()

    def _on_signal():
        logger.info("received shutdown signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    try:
        loop.run_until_complete(run_bot(cfg, stop_event))
    finally:
        loop.close()
        logger.info("daemon stopped")


if __name__ == "__main__":
    main()
