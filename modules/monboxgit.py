import asyncio
import datetime
import logging
import os
import subprocess
import uuid
import yaml
import tempfile
import shutil
from git import Repo

import ansible_runner

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException, AmsServiceException

from argo_automation_cpas.config import get_settings

LOG = logging.getLogger(__name__)

SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY = (
    "argo::mon::amspublisher::publisher_queues_topics"
)
SENSU_BACKEND_PUB_QUEUE_STRING_TEMPLATE = """
Directory : &envrihub_publisher_queue '/var/spool/ams-publisher/{tenant_name}_metrics/'
Rate      : '1'
Host      : messaging_url
Key       : '{ams_token}'
Project   : '{tenant_name}'
Topic     : 'metric_data'
Bulksize  : '1'
MsgType   : 'metric_data'
Avro      : 'True'
AvroSchema: '/etc/ams-publisher/metric_data.avsc'
Retry     : '300'
Timeout   : '60'
SleepRetry: '300'
"""

SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY = "argo::mon::scg::tenant_sections"
SENSU_BACKEND_TENANT_SECTION_STRING_TEMPLATE = """
poem_url       : https://{tenant_name}.poem.devel.mon.argo.grnet.gr
poem_token     : {poem_token}
webapi_token   : {webapi_token}
metricprofiles : default_metric
publish        : 'true'
secrets        : "/etc/sensu/secret_envs"
publisher_queue: "/var/spool/ams-publisher/{tenant_name}_metrics/"
namespace      : auto
"""

SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY = "argo::mon::poemtools::tenants_data"
SENSU_AGENT_STRING_TEMPLATE = """
poem_host : '{poem_host}'
poem_token: '{poem_token}'
profiles  : 'default_metric'
"""


class NewTenantAgentInfo:
    def __init__(self, tenant_name="", tenant_poem_host="", tenant_poem_token=""):
        self.tenant_name = tenant_name
        self.poem_host = tenant_poem_host
        self.poem_token = tenant_poem_token


class NewTenantBackendInfo:
    def __init__(self, tenant_name="", ams_token="", webapi_token="", poem_token=""):
        self.tenant_name = tenant_name
        self.ams_token = ams_token
        self.webapi_token = webapi_token
        self.poem_token = poem_token


class NewTenantEntryInfo:
    def __init__(self, tenant_agent_info, tenant_backend_info):
        self.tenant_agent_info = tenant_agent_info
        self.tenant_backend_info = tenant_backend_info


class MonboxGit:
    def __init__(self):
        self.settings = get_settings()
        self.new_tenant_entries: list[NewTenantEntryInfo] = []

    async def add_new_tenant(self, webapi, ams, new_tenant_name, rest_api_tokens):
        tenant_name_lower = new_tenant_name.lower()

        if self._is_tenant_already_added(tenant_name_lower):
            return

        restApiToken = rest_api_tokens[new_tenant_name]

        if restApiToken is None:
            print(
                "Error: there is no restapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return False

        restApiToken = restApiToken["restapi"]

        monbox_webapi_component = "monbox"
        webapi_tokens = webapi.load_tokens(self.settings.webapi.tokens_spool)
        webapi_tokens = webapi_tokens[new_tenant_name]

        if webapi_tokens is None:
            print(
                "Error: there is no webapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return False

        webapi_token = webapi_tokens[monbox_webapi_component]

        if webapi_token is None:
            print(
                "Error: there is no monbox webapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return False

        monbox_ams_component = "argo-monbox"
        ams_tokens = ams.load_tokens(self.settings.ams.tokens_spool)
        ams_tokens = ams_tokens[new_tenant_name]

        if ams_tokens is None:
            print(
                "Error: there is no ams_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return False

        ams_token = ams_tokens.get(monbox_ams_component)
        if ams_token is None:
            print(
                f"Error: there is no argo-monbox ams_token for tenant with id: {new_tenant_name}; Exiting early."
            )
            return False

        new_tenant_agent_info = NewTenantAgentInfo(
            tenant_name=tenant_name_lower,
            tenant_poem_host=tenant_name_lower + ".poem.devel.mon.argo.grnet.gr",
            tenant_poem_token=restApiToken,
        )

        new_tenant_backend_info = NewTenantBackendInfo(
            tenant_name=tenant_name_lower,
            ams_token=ams_token,
            webapi_token=webapi_token,
            poem_token=restApiToken,
        )

        self._add_tenant_to_array(
            NewTenantEntryInfo(new_tenant_agent_info, new_tenant_backend_info)
        )

    async def commit_new_tenants(self):
        commit_id = (
            str(uuid.uuid4())
            + " | "
            + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S UTC")
        )

        backend_commit_status = await self._commit_sensu_backend_changes(commit_id)
        agent_commit_status = await self._commit_sensu_agent_changes(commit_id)

        return backend_commit_status and agent_commit_status

    async def start_monboxgit_runner(self):
        print(f"MonboxGit | Starting run-puppet script on machines.")

        whoami_cmd = "whoami"
        shell_script_cmd = "/usr/local/bin/run-puppet.sh"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            inventory=f"inventory/{self.settings.ansible.sensu_inventory}",
            host_pattern="sensus",
            module="shell",
            quiet=True,
            module_args=shell_script_cmd,
        )

        kwargs["inventory"] = self.settings.ansible.sensu_inventory

        private_key = self.settings.ansible.ssh_private_key
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        extravars = {}
        extravars["ansible_become"] = "yes"

        kwargs["extravars"] = extravars

        r = await asyncio.to_thread(ansible_runner.run, **kwargs)

        print(f"Runner finished (rc={r.rc})")

        return r.rc

    async def start_monbox_init_check(self):
        print(f"MonboxGit | Starting monbox init check on backend machine(s).")

        whoami_cmd = "whoami"
        shell_script_cmd = "ams-publisherd -q"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            inventory=f"inventory/{self.settings.ansible.sensu_inventory}",
            host_pattern="sensu-backend",
            module="shell",
            quiet=True,
            module_args=shell_script_cmd,
        )

        kwargs["inventory"] = self.settings.ansible.sensu_inventory

        private_key = self.settings.ansible.ssh_private_key
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        extravars = {}
        extravars["ansible_become"] = "yes"

        kwargs["extravars"] = extravars

        r = await asyncio.to_thread(ansible_runner.run, **kwargs)

        print(f"Runner finished (rc={r.rc})")

        all_tenants_inited, inited_tenants = await self._check_if_all_tenants_inited(
            r.events
        )

        return all_tenants_inited, inited_tenants

    async def update_packages_on_backend(self):
        print(f"MonboxGit | Updating packages on backend machine(s).")

        whoami_cmd = "whoami"
        backend_cmd = "python /bin/argo-poem-packages.py && python /bin/scg-reload.py"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            inventory=f"inventory/{self.settings.ansible.sensu_inventory}",
            host_pattern="sensu-backend",
            module="shell",
            quiet=True,
            module_args=backend_cmd,
        )

        kwargs["inventory"] = self.settings.ansible.sensu_inventory

        extravars = {}
        extravars["ansible_become"] = "yes"

        kwargs["extravars"] = extravars

        r = await asyncio.to_thread(ansible_runner.run, **kwargs)

        print(f"Runner finished (rc={r.rc})")

    async def update_packages_on_agent(self):
        print(f"MonboxGit | Updating packages on agent machine(s).")

        whoami_cmd = "whoami"
        agent_cmd = "python /bin/argo-poem-packages.py"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            inventory=f"inventory/{self.settings.ansible.sensu_inventory}",
            host_pattern="sensu-backend",
            module="shell",
            quiet=True,
            module_args=agent_cmd,
        )

        kwargs["inventory"] = self.settings.ansible.sensu_inventory

        extravars = {}
        extravars["ansible_become"] = "yes"

        kwargs["extravars"] = extravars

        r = await asyncio.to_thread(ansible_runner.run, **kwargs)

        print(f"Runner finished (rc={r.rc})")

    def clear_added_tenants(self):
        self.new_tenant_entries.clear()

    def _is_tenant_already_added(self, new_tenant_name):
        for tenant in self.new_tenant_entries:
            if tenant.tenant_agent_info.tenant_name.lower() == new_tenant_name.lower():
                return True

        return False

    def _add_tenant_to_array(self, new_tenant_entry: NewTenantEntryInfo):
        self.new_tenant_entries.append(new_tenant_entry)

    async def _get_sensu_backend_config(self):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        retrieve_branch = self.settings.monboxgit.git_branch_backend
        ssh_key = self.settings.monboxgit.git_ssh_key_path

        file_path = self.settings.monboxgit.backend_config_file_path

        file_data = self._download_github_file_api(
            owner=repo_owner,
            repo=repo_name,
            branch=retrieve_branch,
            path=file_path,
            ssh_key=ssh_key,
        )

        if file_data == False:
            return False

        return file_data

    async def _commit_sensu_backend_changes(self, commit_id=""):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        commit_branch = self.settings.monboxgit.git_branch_backend

        file_data = await self._get_sensu_backend_config()
        if file_data is False:
            print("Error: Unable to fetch sensu backend config. Exiting early.")
            return False

        yaml_data = yaml.safe_load(file_data)

        for agent_info in self.new_tenant_entries:
            yaml_data = self._add_new_tenant_to_backend_yaml(
                yaml_data, agent_info.tenant_backend_info
            )

        file_path = self.settings.monboxgit.backend_config_file_path

        return await self._commit_file_to_git_repo(
            owner=repo_owner,
            repo=repo_name,
            directory=file_path,
            content=yaml.dump(yaml_data, sort_keys=False),
            branch=commit_branch,
            commit_id=commit_id,
        )

    async def _get_sensu_agent_config(self):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        retrieve_branch = self.settings.monboxgit.git_branch_agent
        ssh_key = self.settings.monboxgit.git_ssh_key_path

        file_path = self.settings.monboxgit.agent_config_file_path

        file_data = self._download_github_file_api(
            owner=repo_owner,
            repo=repo_name,
            branch=retrieve_branch,
            path=file_path,
            ssh_key=ssh_key,
        )

        if file_data == False:
            return False

        return file_data

    async def _commit_sensu_agent_changes(self, commit_id=""):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        commit_branch = self.settings.monboxgit.git_branch_agent

        file_data = await self._get_sensu_agent_config()
        if file_data == False:
            print("Error: Unable to fetch sensu backend config. Exiting early.")
            return False

        yaml_data = yaml.safe_load(file_data)

        for agent_info in self.new_tenant_entries:
            yaml_data = self._add_new_tenant_to_agent_yaml(
                yaml_data, agent_info.tenant_agent_info
            )

        file_path = self.settings.monboxgit.agent_config_file_path

        return await self._commit_file_to_git_repo(
            owner=repo_owner,
            repo=repo_name,
            directory=file_path,
            branch=commit_branch,
            content=yaml.dump(yaml_data, sort_keys=False),
            commit_id=commit_id,
        )

    async def _commit_file_to_git_repo(
        self, owner, repo, directory, branch, content="", commit_id=""
    ):

        repo_ssh = f"git@github.com:{owner}/{repo}.git"

        temp_dir = tempfile.mkdtemp()

        success = True
        try:
            repo = Repo.init(temp_dir)
            origin = repo.create_remote("origin", repo_ssh)

            git_ssh_key_path = self.settings.monboxgit.git_ssh_key_path

            # Force Git to use custom SSH key
            os.environ["GIT_SSH_COMMAND"] = (
                f"ssh -i {git_ssh_key_path} -o IdentitiesOnly=yes"
            )

            origin.fetch(branch)
            repo.git.checkout("-b", branch, f"origin/{branch}")

            last_slash_index = directory.rfind("/")
            path_to_file = (
                directory[: (last_slash_index + 1)] if last_slash_index != -1 else ""
            )

            full_target_path = os.path.join(temp_dir, directory)
            os.makedirs(
                os.path.dirname(os.path.join(temp_dir, path_to_file)), exist_ok=True
            )

            if not os.path.isfile(full_target_path):
                try:
                    f = open(full_target_path, "x")
                except FileExistsError as e:
                    print(str(e))
                    raise RuntimeError(
                        "Error: Unable to create file used for commiting to the repo!"
                    )

            f = open(full_target_path, "w")
            f.write(content)
            f.close()

            repo.git.add(all=True)
            repo.index.commit("Upload via Python script\n\nCommit Tag: " + commit_id)

            repo.git.push("origin", f"HEAD:{branch}")

        except e:
            print(str(e))
            success = False
        finally:
            shutil.rmtree(temp_dir)

        return success

    # returns agent yaml file with new tenant; ready for commit
    def _add_new_tenant_to_agent_yaml(self, yaml_data, new_tenant_info):
        tenant_data_entries = yaml_data[SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY]

        # fill string template with tenant data
        new_tenant_agent_string = SENSU_AGENT_STRING_TEMPLATE
        new_tenant_agent_string = new_tenant_agent_string.format(
            poem_host=new_tenant_info.poem_host, poem_token=new_tenant_info.poem_token
        )
        new_tenant_data = yaml.safe_load(new_tenant_agent_string)

        # add yaml tenant entry into tenants array
        yaml_tenant_entry_key = new_tenant_info.tenant_name
        tenant_data_entries[yaml_tenant_entry_key] = new_tenant_data

        # replace old tenants array with new one
        yaml_data[SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY] = tenant_data_entries

        return yaml_data

    # returns backend yaml file with new tenant; ready for commit
    def _add_new_tenant_to_backend_yaml(self, yaml_data, new_tenant_info):
        # NEW TENANT SECTION DATA
        tenant_data_entries = yaml_data[SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY]

        new_tenant_backend_tenant_string = SENSU_BACKEND_TENANT_SECTION_STRING_TEMPLATE
        new_tenant_backend_tenant_string = new_tenant_backend_tenant_string.format(
            tenant_name=new_tenant_info.tenant_name,
            webapi_token=new_tenant_info.webapi_token,
            poem_token=new_tenant_info.poem_token,
        )

        tenant_tenant_entry_key = new_tenant_info.tenant_name
        new_tenant_tenant_data = yaml.safe_load(new_tenant_backend_tenant_string)
        tenant_data_entries[tenant_tenant_entry_key] = new_tenant_tenant_data

        yaml_data[SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY] = tenant_data_entries

        # NEW TENANT PUB QUEUE DATA
        tenant_pub_queue_entries = yaml_data.get(SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY)

        new_tenant_backend_pub_queue_string = SENSU_BACKEND_PUB_QUEUE_STRING_TEMPLATE
        new_tenant_backend_pub_queue_string = (
            new_tenant_backend_pub_queue_string.format(
                tenant_name=new_tenant_info.tenant_name,
                ams_token=new_tenant_info.ams_token,
            )
        )

        tenant_pub_queue_entry_key = "Metrics" + new_tenant_info.tenant_name
        new_tenant_pub_queue_data = yaml.safe_load(new_tenant_backend_pub_queue_string)
        tenant_pub_queue_entries[tenant_pub_queue_entry_key] = new_tenant_pub_queue_data

        yaml_data[SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY] = tenant_pub_queue_entries

        return yaml_data

    def _download_github_file_api(
        self,
        owner,
        repo,
        path="data/default.yaml",
        ssh_key="",
        branch="sensu_backend_auto_devel_mon_argo_grnet_gr",
    ):

        if len(ssh_key) == 0 or ssh_key is None:
            print("download_github_file_api | ssh_key is invalid; exiting early")
            return False

        env = os.environ
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key} -o StrictHostKeyChecking=no"

        url = f"git@github.com:{owner}/{repo}.git"

        file_data = ""

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "-b",
                    branch,
                    "--single-branch",
                    url,
                    tmp,
                ],
                env=env,
                check=True,
            )

            with open(os.path.join(tmp, path), "rb") as f:
                file_data = f.read()

        return file_data

    async def _check_if_all_tenants_inited(self, events):
        line_prefix = "INFO - worker:metrics"
        line_prefix_len = len(line_prefix)
        inited_tenants = []

        for event in events:
            if event.get("event", "") == "runner_on_ok":
                # this is the output of the run command
                result = event["event_data"]["res"]["stdout"]
                lines = result.split("\n")
                for line in lines:
                    if line.find("published") == -1:
                        continue

                    # get name of tenant
                    first_reverse_whitespace = line.rfind(" ")
                    tenant_name = line[line_prefix_len:first_reverse_whitespace]
                    tenant_name_lower = tenant_name.lower()

                    found_tenant = self._is_tenant_already_added(tenant_name_lower)
                    if not found_tenant:
                        continue

                    # get the published number
                    published_string = line[first_reverse_whitespace + 1 :]
                    published_string_split = published_string.split(":")
                    published_number = int(published_string_split[1])

                    # confirm the monbox was initialized (published must be > 0)
                    if published_number > 0:
                        print(f"Tenant {tenant_name_lower} monbox init confirmed.")
                        inited_tenants.append(tenant_name_lower)

        return len(inited_tenants) == len(self.new_tenant_entries), inited_tenants
