import argparse
import asyncio
import logging

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import DEFAULT_ANSIBLE_PLAYBOOK, get_settings
from argo_automation_cpas.log import setup_logging


def parse_args():
    parser = argparse.ArgumentParser(description="ARGO CPAS automation controller")
    parser.add_argument(
        "--only-ansible",
        nargs="?",
        const=DEFAULT_ANSIBLE_PLAYBOOK,
        default=None,
        metavar="PLAYBOOK",
        help=(
            "Run only the Ansible playbook without contacting AMS, Web API or IAM. "
            "Optionally specify a playbook filename (default: %(const)s)"
        ),
    )
    parser.add_argument(
        "--inventory",
        default=None,
        metavar="INVENTORY",
        help="Inventory file or directory to use instead of the default inventory/",
    )
    parser.add_argument(
        "--show-artifacts",
        action="store_true",
        default=False,
        help="Print ansible-runner stdout and stderr after the run finishes",
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

    app = Application(
        settings,
        only_ansible=args.only_ansible,
        inventory=args.inventory,
        show_artifacts=args.show_artifacts,
    )
    asyncio.run(app.run())
