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
        nargs="*",
        default=None,
        metavar="ROLE",
        help=(
            "Print ansible-runner stdout and stderr after the run finishes. "
            "Optionally filter stdout to tasks from specific role(s)."
        ),
    )
    parser.add_argument(
        "--clean-artifacts",
        nargs="*",
        default=None,
        metavar="ROLE",
        help=(
            "Remove ansible-runner artifact directories and exit. "
            "Without arguments removes all artifacts. "
            "With role name(s) removes only runs that contain tasks from those role(s)."
        ),
    )
    parser.add_argument(
        "--only-ams",
        action="store_true",
        default=False,
        help="Pull one message from the AMS subscription, print it, and exit.",
    )
    parser.add_argument(
        "--only-webapi",
        action="store_true",
        default=False,
        help="Probe the Web API and fetch topology config, then exit.",
    )
    parser.add_argument(
        "--only-iam",
        action="store_true",
        default=False,
        help="Fetch an IAM OIDC token, print it, and exit.",
    )
    parser.add_argument(
        "--add-tenants",
        nargs="+",
        default=None,
        metavar="TENANT",
        help="Tenant name(s) to add or update (sets connector_add_tenants extravars).",
    )
    parser.add_argument(
        "--remove-tenants",
        nargs="+",
        default=None,
        metavar="TENANT",
        help="Tenant name(s) to remove (sets connector_remove_tenants extravars).",
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
        only_ams=args.only_ams,
        only_webapi=args.only_webapi,
        only_iam=args.only_iam,
        inventory=args.inventory,
        show_artifacts=args.show_artifacts,
        clean_artifacts=args.clean_artifacts,
        add_tenants=args.add_tenants,
        remove_tenants=args.remove_tenants,
    )
    asyncio.run(app.run())
