import logging
import os
import re
import shutil

LOG = logging.getLogger(__name__)

_TASK_RE = re.compile(r"^TASK \[(?P<role>[^\]]+?) : [^\]]+\]")
_WIDTH = 72


def _role_of(line):
    m = _TASK_RE.match(line)
    return m.group("role").strip() if m else None


def _filter_stdout(content, roles):
    if not roles:
        return content

    result = []
    include_block = False

    for line in content.splitlines():
        if line.startswith("PLAY [") or line.startswith("PLAY RECAP"):
            include_block = False
            result.append(line)
        elif line.startswith("TASK ["):
            role = _role_of(line)
            include_block = role in roles
            if include_block:
                if result and result[-1] != "":
                    result.append("")
                result.append(line)
        elif include_block:
            result.append(line)

    return "\n".join(result)


def print_artifacts(runner, roles):
    try:
        stdout = runner.stdout.read().strip()
    except Exception:
        stdout = ""

    try:
        stderr = runner.stderr.read().strip()
    except Exception:
        stderr = ""

    stdout = _filter_stdout(stdout, roles)

    for label, content in (("STDOUT", stdout), ("STDERR", stderr)):
        print("\n" + "=" * _WIDTH)
        if roles and label == "STDOUT":
            print(f"  {label}  [roles: {', '.join(roles)}]")
        else:
            print(f"  {label}")
        print("=" * _WIDTH)
        if content:
            for line in content.splitlines():
                print(f"  {line}")
        else:
            print("  (empty)")

    print("=" * _WIDTH + "\n")


def clean_artifacts(artifacts_dir, roles):
    if not os.path.isdir(artifacts_dir):
        LOG.info("Artifacts directory does not exist: %s", artifacts_dir)
        return

    if not roles:
        shutil.rmtree(artifacts_dir)
        os.makedirs(artifacts_dir)
        LOG.info("Removed all artifacts from %s", artifacts_dir)
        return

    roles_set = set(roles)
    removed = 0

    for entry in os.scandir(artifacts_dir):
        if not entry.is_dir():
            continue

        stdout_path = os.path.join(entry.path, "stdout")
        try:
            with open(stdout_path) as fh:
                content = fh.read()
        except OSError:
            continue

        if any(
            re.search(r"TASK \[" + re.escape(role) + r" : ", content)
            for role in roles_set
        ):
            shutil.rmtree(entry.path)
            LOG.info("Removed artifact run %s", entry.name)
            removed += 1

    LOG.info(
        "Removed %d artifact run(s) matching role(s): %s",
        removed, ", ".join(sorted(roles_set)),
    )
