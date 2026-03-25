import argparse
import asyncio
import logging

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.log import setup_logging


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

    try:
        settings = get_settings()
    except FileNotFoundError as exc:
        logging.basicConfig()
        logging.error("%s", exc)
        raise SystemExit(1)

    setup_logging(settings)

    app = Application(settings, only_ansible=args.only_ansible)
    asyncio.run(app.run())
