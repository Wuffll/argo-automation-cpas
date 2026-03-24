import asyncio
import logging

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import get_settings


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main():
    configure_logging()
    app = Application(get_settings())
    asyncio.run(app.run())
