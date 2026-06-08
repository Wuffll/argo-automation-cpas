import asyncio
import datetime
import json
import logging
import os
import subprocess
import uuid
import yaml
import requests
import base64
import tempfile
import shutil
from git import Repo

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException, AmsServiceException

from argo_automation_cpas.config import get_settings

LOG = logging.getLogger(__name__)

SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY = "argo::mon::amspublisher::publisher_queues_topics"
SENSU_BACKEND_PUB_QUEUE_STRING_TEMPLATE = '''
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
'''

SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY = "argo::mon::scg::tenant_sections"
SENSU_BACKEND_TENANT_SECTION_STRING_TEMPLATE = '''
poem_url       : https://{tenant_name}.poem.devel.mon.argo.grnet.gr
poem_token     : Hj38v7mZocJMMk4D9mbH9lFfRjnB5Jgf
webapi_token   : {webapi_token}
metricprofiles : default_metric
publish        : 'true'
secrets        : "/etc/sensu/secret_envs"
publisher_queue: "/var/spool/ams-publisher/{tenant_name}_metrics/"
namespace      : poc
'''

SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY = "argo::mon::poemtools::tenants_data"
SENSU_AGENT_STRING_TEMPLATE = """
poem_host : '{poem_host}'
poem_token: '{poem_token}'
profiles  : 'default_metric'
"""

class NewTenantAgentInfo:
    def __init__(self, tenant_id = "", tenant_poem_host = "", tenant_poem_token = ""):
        self.tenant_id = tenant_id
        self.poem_host = tenant_poem_host
        self.poem_token = tenant_poem_token

class NewTenantBackendInfo:
    def __init__(self, tenant_id = "", ams_token = "", webapi_token = ""):
        self.tenant_id = tenant_id
        self.ams_token = ams_token
        self.webapi_token = webapi_token

class MonboxGit:
    def __init__(self):
        self.settings = get_settings()

    async def init_new_tenant(self, tenant_backend_info, tenant_agent_info):
        commit_id = str(uuid.uuid4()) + " | " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S UTC")

        await self._commit_sensu_backend_changes(tenant_backend_info, commit_id)
        await self._commit_sensu_agent_changes(tenant_agent_info, commit_id)

    async def _commit_sensu_backend_changes(self, tenant_backend_info, commit_id=""):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        commit_branch = self.settings.monboxgit.git_branch_backend
        ssh_key = self.settings.monboxgit.git_ssh_key_path

        file_path = "data/default.yaml"

        file_data = self._download_github_file_api(owner=repo_owner,
                                                   control_repo=repo_name,
                                                   branch=commit_branch,
                                                   path=file_path,
                                                   ssh_key=ssh_key)

        yaml_data = yaml.safe_load(file_data)
        

        new_tenant_id = tenant_backend_info.tenant_id
        new_tentant_ams_token = tenant_backend_info.ams_token
        new_tenant_webapi_token = tenant_backend_info.webapi_token

        new_tenant_info = NewTenantBackendInfo(tenant_id=new_tenant_id,
                                               ams_token=new_tentant_ams_token,
                                               webapi_token=new_tenant_webapi_token)

        yaml_data = self._add_new_tenant_to_backend_yaml(yaml_data, new_tenant_info)

        await self._commit_file_to_git_repo(owner=repo_owner,
                                            repo=repo_name,
                                            directory=file_path,
                                            content=yaml.dump(yaml_data, sort_keys=False),
                                            branch=commit_branch,
                                            commit_id=commit_id)

    async def _commit_sensu_agent_changes(self, tenant_agent_info, commit_id=""):
        repo_owner = self.settings.monboxgit.git_repo_owner
        repo_name = self.settings.monboxgit.git_repo_name
        commit_branch = self.settings.monboxgit.git_branch_agent
        ssh_key = self.settings.monboxgit.git_ssh_key_path

        file_path = "data/default.yaml"

        file_data = self._download_github_file_api(owner=repo_owner,
                                                   control_repo=repo_name,
                                                   branch=commit_branch,
                                                   path=file_path,
                                                   ssh_key=ssh_key)
        yaml_data = yaml.safe_load(file_data)
        
        
        new_tenant_id = tenant_agent_info.tenant_id
        new_tentant_poem_host = tenant_agent_info.poem_host
        new_tenant_poem_token = tenant_agent_info.poem_token

        new_tenant_info = NewTenantAgentInfo(tenant_id = new_tenant_id,
                                             tenant_poem_host= new_tentant_poem_host,
                                             tenant_poem_token= new_tenant_poem_token)

        yaml_data = self._add_new_tenant_to_agent_yaml(yaml_data, new_tenant_info)

        await self._commit_file_to_git_repo(owner=repo_owner,
                                            repo=repo_name,
                                            directory=file_path,
                                            branch=commit_branch,
                                            content=yaml.dump(yaml_data, sort_keys=False),
                                            commit_id=commit_id)

    async def _commit_file_to_git_repo(self,
                                       owner,
                                       repo,
                                       directory,
                                       branch,
                                       content="",
                                       commit_id=""):

        repo_ssh = f"git@github.com:{owner}/{repo}.git"

        temp_dir = tempfile.mkdtemp()
        
        try:
            repo = Repo.init(temp_dir)
            origin = repo.create_remote("origin", repo_ssh)

            git_ssh_key_path = self.settings.monboxgit.git_ssh_key_path

            os.environ["GIT_SSH_COMMAND"] = f"ssh -i {git_ssh_key_path} -o IdentitiesOnly=yes"

            origin.fetch(branch)
            repo.git.checkout("-b", branch, f"origin/{branch}")

            last_slash_index = directory.rfind("/")
            path_to_file = directory[:(last_slash_index + 1)] if last_slash_index != -1 else ""

            full_target_path = os.path.join(temp_dir, directory)
            os.makedirs(os.path.dirname(os.path.join(temp_dir, path_to_file)), exist_ok=True)

            if not os.path.isfile(full_target_path):
                try:
                    f = open(full_target_path, "x")
                except FileExistsError as e:
                    print(str(e))
                    print("Error: Unable to create file used for commiting to the repo!")
                    return

            f = open(full_target_path, "w")
            f.write(content)
            f.close()

            repo.git.add(all=True)
            repo.index.commit("Upload via Python script\n\nCommit Tag: " + commit_id)

            # Force Git to use custom SSH key

            repo.git.push("origin", f"HEAD:{branch}")

        finally:
            shutil.rmtree(temp_dir)

    # returns agent yaml file with new tenant; ready for commit
    def _add_new_tenant_to_agent_yaml(self, yaml_data, new_tenant_info):
        tenant_data_entries = yaml_data[SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY]

        # fill string template with tenant data
        new_tenant_agent_string = SENSU_AGENT_STRING_TEMPLATE
        new_tenant_agent_string = new_tenant_agent_string.format(poem_host=new_tenant_info.poem_host,
                                                                 poem_token=new_tenant_info.poem_token)
        new_tenant_data = yaml.safe_load(new_tenant_agent_string)

        # add yaml tenant entry into tenants array
        yaml_tenant_entry_key = new_tenant_info.tenant_id
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
            tenant_name=new_tenant_info.tenant_id,
            webapi_token=new_tenant_info.webapi_token,)

        tenant_tenant_entry_key = new_tenant_info.tenant_id
        new_tenant_tenant_data = yaml.safe_load(new_tenant_backend_tenant_string)
        tenant_data_entries[tenant_tenant_entry_key] = new_tenant_tenant_data

        yaml_data[SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY] = tenant_data_entries

        # NEW TENANT PUB QUEUE DATA
        tenant_pub_queue_entries = yaml_data.get(SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY)

        new_tenant_backend_pub_queue_string = SENSU_BACKEND_PUB_QUEUE_STRING_TEMPLATE
        new_tenant_backend_pub_queue_string = new_tenant_backend_pub_queue_string.format(
            tenant_name=new_tenant_info.tenant_id,
            ams_token=new_tenant_info.ams_token,)

        tenant_pub_queue_entry_key = "Metrics" + new_tenant_info.tenant_id
        new_tenant_pub_queue_data = yaml.safe_load(new_tenant_backend_pub_queue_string)
        tenant_pub_queue_entries[tenant_pub_queue_entry_key] = new_tenant_pub_queue_data

        yaml_data[SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY] = tenant_pub_queue_entries

        return yaml_data

    def _download_github_file_api(self,
                                  owner,
                                  repo,
                                  path = "data/default.yaml",
                                  ssh_key="",
                                  branch="sensu_backend_auto_devel_mon_argo_grnet_gr"):
        
        if len(ssh_key) == 0 or ssh_key is None:
            print("download_github_file_api | ssh_key is invalid; exiting early")
            return

        env = os.environ
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key} -o StrictHostKeyChecking=no"

        url = f"git@github.com:{owner}/{repo}.git"

        file_data = ""

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", branch, "--single-branch", url, tmp],
                env=env,
                check=True,
            )

            with open(os.path.join(tmp, path), "rb") as f:
                file_data = f.read()

        return file_data