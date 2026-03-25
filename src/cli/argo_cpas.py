import argparse
import asyncio
import logging

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import get_settings


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="ARGO CPAS automation controller")
    parser.add_argument(
        "--only-ansible",
        action="store_true",
        default=False,
        help="Run only the Ansible playbook without contacting AMS, Web API or IAM",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    configure_logging()

    try:
        settings = get_settings()
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        raise SystemExit(1)

    app = Application(settings, only_ansible=args.only_ansible)
    asyncio.run(app.run())
