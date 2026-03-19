from __future__ import annotations

import asyncio
import logging

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import get_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    app = Application(get_settings())
    asyncio.run(app.run())
