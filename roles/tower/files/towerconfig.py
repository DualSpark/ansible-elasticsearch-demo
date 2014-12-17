#!/usr/env/python
import os
from subprocess import call

with open('/etc/boto.cfg', 'r') as f:
    filedata = f.readlines()

config_data = {}
for line in filedata:
	if '=' in line:
		parts = [x.strip() for x in line.split('=')]
		config_data[parts[0]] = parts[1]


org_create = ['tower-cli', 'organization', 'create', '--name', '"ElkEnvironment Demo"']
inv_create = ['tower-cli', 'inventory', 'create', '--name', '"AWS Demo Environment"', '--description', '"Demo Environment inventory for AWS Elasticsearch demo"', '--organization', '1', '--variables', '/tmp/tower_group.yml']
cred_create = ['tower-cli', 'credential', 'create', '--name', 'AWSCloudCredentials', '--user', 'admin', '--kind', 'aws', '--username', config_data['aws_access_key_id'], '--password', config_data['aws_secret_access_key']]
group_create = ['tower-cli', 'group', 'create', '--name', '"ElkDemo Group"', '--inventory', '1', '--variables', '/tmp/tower_group.yml', '--source', 'ec2', '--credential', '1']
group_update = ['tower-cli', 'group', 'sync', '1']

call(org_create)
call(inv_create)
call(cred_create)
call(group_create)
call(group_update)
