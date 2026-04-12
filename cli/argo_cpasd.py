import argparse
import asyncio
import logging
import signal

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.log import setup_logging


LOG = logging.getLogger(__name__)

DEFAULT_SLEEP = 60


def parse_args():
    parser = argparse.ArgumentParser(description="ARGO CPAS automation daemon")
    parser.add_argument(
        "--sleep",
        type=int,
        default=DEFAULT_SLEEP,
        metavar="SECONDS",
        help="Seconds to sleep between AMS poll cycles (default: %(default)s)",
    )
    return parser.parse_args()


async def loop(settings, sleep):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    LOG.info("Daemon started, polling every %ds", sleep)

    while not stop.is_set():
        try:
            app = Application(settings)
            await app.run()
        except Exception:
            LOG.exception("Unhandled error in pipeline cycle")

        try:
            await asyncio.wait_for(stop.wait(), timeout=sleep)
        except asyncio.TimeoutError:
            pass

    LOG.info("Daemon stopped")


def main():
    args = parse_args()

    try:
        settings = get_settings()
    except FileNotFoundError as exc:
        logging.basicConfig()
        logging.error("%s", exc)
        raise SystemExit(1)

    setup_logging(settings)

    asyncio.run(loop(settings, args.sleep))
