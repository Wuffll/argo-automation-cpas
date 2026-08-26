#! /bin/bash

ansible-playbook /opt/argoeu-automation-repo/performance-data.yml \
       	--inventory /opt/argoeu-automation-repo/performance-data.ini \
	--vault-pass-file /opt/argoeu-automation-repo/.ansible/.vault_pass

