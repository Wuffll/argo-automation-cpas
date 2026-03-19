from __future__ import annotations

import asyncio
import logging

from .app import Application
from .config import get_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    app = Application(get_settings())
    asyncio.run(app.run())
