# argo-automation-cpas

Automation service for the dynamic configuration of ARGO components: Connectors, POEM, Archiver and Sensu (CPAS). The service listens to an ARGO Messaging Service (AMS) subscription for tenant events, fetches configuration from the ARGO Web API, obtains OIDC tokens from an IAM provider, reports automation status, and drives Ansible playbooks via `ansible-runner` to provision or remove connector instances on target hosts.

## Features

- Asynchronous event-driven architecture built on `aiohttp`
- Daemon mode (`argo-cpasd`) with configurable poll interval for continuous operation
- Pulls tenant provisioning events from AMS subscriptions
- Fetches topology configuration and refreshes component tokens via the ARGO Web API
- Obtains and caches OIDC access tokens from an IAM identity provider
- Reports automation progress to a Status API
- Executes Ansible playbooks through `ansible-runner` to add or remove connector tenants
- Manages Ansible artifacts (inspect, filter by role, clean up)
- Flexible logging to stdout, file, and/or syslog
- CLI with granular `--only-*` flags for testing individual subsystems in isolation
- Singleton configuration shared across all service modules

## Requirements

- Python 3.12+
- Poetry 2.x

## Installation

```bash
poetry install
```

For development (includes ruff, pdbpp):

```bash
poetry install --with devel
```

## Usage

```bash
# full pipeline: pull AMS event -> fetch config -> run ansible
poetry run argo-cpas

# run as a daemon (polls AMS every daemon_sleep seconds)
poetry run argo-cpasd

# run daemon with custom sleep interval (overrides config)
poetry run argo-cpasd --sleep 120

# run only a specific ansible playbook
poetry run argo-cpas --only-ansible connectors.yml

# run ansible with a custom inventory
poetry run argo-cpas --only-ansible connectors.yml --inventory /path/to/inventory

# add tenants
poetry run argo-cpas --only-ansible connectors.yml --add-tenants TENANT-A TENANT-B

# remove tenants
poetry run argo-cpas --only-ansible connectors.yml --remove-tenants TENANT-C

# pull and print one AMS message (no ack)
poetry run argo-cpas --only-ams

# move subscription offset back 10 messages and pull
poetry run argo-cpas --only-ams --offset -10

# move subscription offset forward 5 messages and pull
poetry run argo-cpas --only-ams --offset +5

# filter AMS messages by configured tenants and events
poetry run argo-cpas --only-ams --filter-events

# probe Web API and refresh component tokens
poetry run argo-cpas --only-webapi

# fetch and print an OIDC token from IAM
poetry run argo-cpas --only-iam

# fetch automation status for a tenant
poetry run argo-cpas --only-statusapi <TENANT_ID>

# update automation status for a tenant event
poetry run argo-cpas --only-statusapi <TENANT_ID> --update-status IN_PROGRESS --event INIT_TOPOLOGY_CONNECTOR

# show ansible-runner artifacts (optionally filter by role)
poetry run argo-cpas --only-ansible --show-artifacts connector

# clean all ansible-runner artifacts
poetry run argo-cpas --clean-artifacts

# clean artifacts only for specific roles
poetry run argo-cpas --clean-artifacts connector
```

### CLI flags (`argo-cpas`)

| Flag                            | Description                                                                                                                       |
|---------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `--only-ansible [PLAYBOOK]`     | Run only the Ansible playbook without contacting AMS, Web API or IAM. Defaults to `init.yml` if no playbook is specified.         |
| `--inventory INVENTORY`         | Inventory file or directory to use instead of the default `ansible/inventory/`.                                                   |
| `--add-tenants TENANT [...]`    | Tenant name(s) to add or update (populates `connector_tenants` extravars).                                                        |
| `--remove-tenants TENANT [...]` | Tenant name(s) to remove (populates `connector_remove_tenants` extravars).                                                        |
| `--show-artifacts [ROLE ...]`   | Print ansible-runner stdout/stderr after a run. Optionally filter output to tasks from specific role(s).                          |
| `--clean-artifacts [ROLE ...]`  | Remove ansible-runner artifact directories and exit. Without arguments removes all; with role name(s) removes only matching runs. |
| `--only-ams`                    | Pull one message from the AMS subscription (without ack), print it, and exit.                                                     |
| `--offset N`                    | Used with `--only-ams`. Move subscription offset by N messages before pulling (e.g. `+10` forward, `-10` back).                   |
| `--filter-events`               | Used with `--only-ams`. Print only messages matching `automation.tenants` and `ams.events` from the config.                       |
| `--only-webapi`                 | Probe the Web API and fetch/refresh component tokens, then exit.                                                                  |
| `--only-iam`                    | Fetch an IAM OIDC token, print it, and exit.                                                                                      |
| `--only-statusapi TENANT_ID`    | Fetch automation status for the given tenant ID from the Status API and exit.                                                     |
| `--update-status STATUS`        | Used with `--only-statusapi` and `--event`. PATCH a job status (e.g. `IN_PROGRESS`, `DONE`, `ERROR`) for the given tenant/event.  |
| `--event EVENT`                 | Event name used with `--update-status` (e.g. `INIT_TOPOLOGY_CONNECTOR`).                                                          |
| `--message MESSAGE`             | Used with `--update-status`. Override the default job message (`Event picked up by argo-automation-cpas`).                        |

### CLI flags (`argo-cpasd`)

| Flag              | Description                                                                       |
|-------------------|-----------------------------------------------------------------------------------|
| `--sleep SECONDS` | Seconds to sleep between AMS poll cycles. Overrides `daemon_sleep` from config.   |

## Project layout

```
cli/
  argo_cpas.py              # CLI entrypoint and argument parsing
  argo_cpasd.py             # Daemon entrypoint with poll loop
modules/
  app.py                    # Application class orchestrating the full pipeline
  config.py                 # INI config parser and Settings singleton
  log.py                    # Logging setup (stdout, file, syslog)
  ams.py                    # AMS client initialisation, message pull and decode
  webapi.py                 # Web API topology config, token refresh
  iam.py                    # OIDC token fetch and cache
  statusapi.py              # Status API reporting and querying
  http.py                   # SessionWithRetry: aiohttp session with retry logic
  artifacts.py              # Ansible artifact printing and cleanup
  ansible.py                # ansible-runner execution with extravars
init/
  argo-cpasd.service        # systemd unit file for the daemon
ansible/
  project/
    init.yml                # Bootstrap/demo playbook
    connectors.yml          # Main connectors playbook
    ansible.cfg             # Ansible configuration
  inventory/
    connectors.ini          # Default inventory
  roles/
    connector/              # Connector role (tasks, templates, defaults, handlers)
config/
  argo-cpas.conf.template   # Configuration file template
  roles-defaults.yml        # Default Ansible extravars for connectors
  tokens.yml                # Manual connector tokens (per-tenant Web API tokens)
docker/
  Dockerfile.controller_ubuntu  # Container image for the controller
version.py                  # Version string (0.1.0)
Makefile                    # Build targets (wheel-prod, wheel-devel, clean)
pyproject.toml              # Project metadata and tool configuration
```

## Configuration

The service is configured through an INI file. By default it looks for the config file at:

1. `/opt/argo-automation-cpas/etc/argo-cpas.conf`
2. `/etc/argo-cpas.conf`

You can override the path by setting the `ARGO_CPAS_CONFIG` environment variable or by passing a path programmatically to `load_config()`.

A template is provided in `config/argo-cpas.conf.template`.

### `[DEFAULT]` section

| Option | Description                                                                                                                                                         | Example                      |
|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|
| `VENV` | Base installation directory. Used as a prefix for derived paths (log files, spool, ansible data). The `%(VENV)s` interpolation syntax can be used in other options. | `/opt/argo-automation-cpas/` |


### `[general]` section

| Option            | Description                                                                                     | Default                         |
|-------------------|-------------------------------------------------------------------------------------------------|---------------------------------|
| `loggers`         | Comma-separated list of log handlers to activate. Supported values: `stdout`, `file`, `syslog`. | _(none)_                        |
| `log_level`       | Python logging level name.                                                                      | `INFO`                          |
| `log_file`        | Path to the log file (used when `file` is in `loggers`). Supports `%(VENV)s` interpolation.     | `%(VENV)svar/log/argo-cpas.log` |
| `syslog_address`  | Unix socket path or `host:port` for the syslog handler.                                         | `/dev/log`                      |
| `syslog_facility` | Syslog facility name (e.g. `user`, `local0`, `daemon`).                                         | `user`                          |
| `request_timeout` | HTTP request timeout in seconds for all `aiohttp` sessions.                                     | `30.0`                          |
| `verify_ssl`      | Whether to verify TLS certificates.                                                             | `true`                          |
| `retries`         | Number of retry attempts on HTTP connection errors.                                             | `3`                             |
| `retry_delay`     | Base delay in seconds between retries (linear backoff).                                         | `1.0`                           |
| `strip_ansi`      | Strip ANSI color codes from Ansible output by setting `ANSIBLE_NOCOLOR=1`.                      | `true`                          |
| `daemon_sleep`    | Seconds to sleep between AMS poll cycles in daemon mode (`argo-cpasd`).                         | `60`                            |

### `[automation]` section

| Option    | Description                                                                                                                                       | Example              |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|
| `tenants` | Comma-separated list of tenant names the service manages. Used to filter AMS events and iterate over tenants for Web API token refresh.            | `TENANT-A, TENANT-B` |

### `[ams]` section

Configuration for the ARGO Messaging Service connection.

| Option               | Description                                                                                                                                                                           | Example                       |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------|
| `project`            | AMS project name.                                                                                                                                                                     | `ARGO-MON-AUTOMATION`         |
| `host`               | AMS API hostname (without `https://` prefix).                                                                                                                                         | `api.devel.msg.argo.grnet.gr` |
| `subscription`       | AMS subscription name to pull events from.                                                                                                                                            | `events-sub-2`                |
| `token`              | AMS authentication token.                                                                                                                                                             | _(secret)_                    |
| `pullmsgs`           | Maximum number of messages to pull per request (used as `num` for `pullack_sub`/`pull_sub`). Default: `1`.                                                                            | `10`                          |
| `ack`                | Whether to acknowledge pulled messages in the main pipeline. `true` uses `pullack_sub` (pull + ack), `false` uses `pull_sub` (pull without ack). Default: `false`.                    | `false`                       |
| `return_immediately` | Whether pull requests return immediately when no messages are available. Default: `true`.                                                                                              | `true`                        |
| `events`             | Comma-separated list of event types the service reacts to. Default: `INIT_TOPOLOGY_CONNECTOR`.                                                                                        | `INIT_TOPOLOGY_CONNECTOR`     |

The service constructs the full AMS URL as `https://<host>` automatically. The `--only-ams` flag always pulls without ack regardless of the `ack` setting.

### `[webapi]` section

Configuration for the ARGO Web API.

| Option                  | Description                                                                                                 | Example                                                                            |
|-------------------------|-------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| `host`                  | Web API hostname (without `https://` prefix).                                                               | `api.devel.mon.argo.grnet.gr`                                                      |
| `url_api_config`        | API path for fetching topology configuration feeds.                                                         | `/api/v2/feeds/topology`                                                           |
| `url_api_integrations`  | API path template for refreshing component tokens. Supports `{component}` and `{tenant_name}` placeholders. | `/api/v3/integrations/components/{component}/by-tenant-name/{tenant_name}/refresh` |
| `token_component_admin` | Admin API token used for component token refresh requests.                                                  | _(secret)_                                                                         |
| `components`            | Comma-separated list of component names whose tokens should be refreshed.                                   | `monbox, connector, poem-admin, poem-viewer`                                       |

The full Web API URL is constructed as `https://<host>`. Refreshed tokens are cached in `<VENV>/var/spool/webapi_tokens.json`.

### `[statusapi]` section (optional)

| Option | Description                                                                            | Example                                                                               |
|--------|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| `api`  | Full URL template for the Status API endpoint. Must contain `{tenant_id}` placeholder. | `https://api-status.devel.mon.argo.grnet.gr/v1/automation/tenants/{tenant_id}/status` |


### `[iam]` section

Configuration for the OIDC identity provider used to obtain access tokens.

| Option               | Description                                          | Example                                                                                |
|----------------------|------------------------------------------------------|----------------------------------------------------------------------------------------|
| `api`                | Full OIDC token endpoint URL.                        | `https://login-devel.einfra.grnet.gr/auth/realms/einfra/protocol/openid-connect/token` |
| `oidc_client_id`     | OAuth2 client ID for the `client_credentials` grant. | `topology.connector.integration.service`                                               |
| `oidc_client_secret` | OAuth2 client secret.                                | _(secret)_                                                                             |

Obtained tokens are cached in `<VENV>/var/spool/iam_access.yml` and reused until 30 seconds before expiry.

### `[ansible]` section (optional)

Configuration for the Ansible connector playbook runs.

| Option                 | Description                                                                                                                                                                          | Default          |
|------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------|
| `user_connector`       | OS user that owns connector files on target hosts. Passed as `user_connector` extravar.                                                                                              | _(empty)_        |
| `group_connector`      | OS group that owns connector files on target hosts. Passed as `group_connector` extravar.                                                                                            | _(empty)_        |
| `ssh_private_key`      | Path to the SSH private key used by `ansible-runner` for remote connections.                                                                                                         | _(empty)_        |
| `defaults_file`        | Path to a YAML file with default Ansible extravars for connector runs. Keys prefixed with `connector_tenant_` are treated as per-tenant defaults. Supports `%(VENV)s` interpolation. | _(empty)_        |
| `tokens_manual`        | Path to a YAML file containing manual connector tokens. The file must have a top-level `connector_tokens` mapping. Supports `%(VENV)s` interpolation.                                | _(empty)_        |
| `connectors_playbook`  | Filename of the connectors playbook inside `ansible/project/`.                                                                                                                       | `connectors.yml` |
| `connectors_inventory` | Filename of the connectors inventory inside `ansible/inventory/`.                                                                                                                    | `connectors.ini` |
| `poem_restapi_token`   | Path to the JSON file used to cache generated POEM REST-API tenant tokens. Supports `%(VENV)s` interpolation.                                                                        | `<VENV>/var/spool/restapi_tokens.json` |


### Ansible roles-defaults file (`roles-defaults.yml`)

Referenced by `defaults_file` in the `[ansible]` section. This YAML file provides default extravars for connector playbook runs. Key conventions:

- Keys prefixed with `connector_tenant_` are extracted as per-tenant defaults and merged into each tenant's configuration
- These per-tenant defaults can be overridden by topology config fetched from the Web API at runtime
- All other keys are passed as global extravars to `ansible-runner`

### Ansible tokens file (`tokens.yml`)

Referenced by `tokens_manual` in the `[ansible]` section. Structure:

```yaml
connector_tokens:
  <tenant_name>:
    webapi: <TOKEN>
```

These tokens are passed as the `connector_tokens` extravar to Ansible, making per-tenant Web API tokens available to playbook templates.

## Hardcoded defaults

The following values are hardcoded and not currently exposed in the configuration file:

| Setting                    | Value            | Description                                                |
|----------------------------|------------------|------------------------------------------------------------|
| `ansible_playbook`         | `init.yml`       | Default playbook used in the full pipeline (AMS-triggered) |
| `ansible_private_data_dir` | `<VENV>/ansible` | Base directory for `ansible-runner`                        |

## Systemd

A systemd unit file is provided at `init/argo-cpasd.service`. Install it to `/usr/lib/systemd/system/` and enable it:

```bash
systemctl daemon-reload
systemctl enable --now argo-cpasd
```

## Building

```bash
# production wheel
make wheel-prod

# development wheel (appends date-based .dev suffix to version)
make wheel-devel
```

## License

Apache License 2.0
