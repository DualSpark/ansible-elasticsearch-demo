#!/usr/env/python
'''
demokeys.py

Usage: 
    demokeys.py create [--aws_region <AWS_REGION>] [--param_file <PARAM_FILE>] [--key_file <KEY_FILE>]
    demokeys.py cleanup [--aws_region <AWS_REGION>] [--key_file <KEY_FILE>] [--delete_files]

Options: 
  -h --help                  Show this screen.
  -v --version               Show version.
  --key_file <KEY_FILE>      path to save the output [Default: awskeys.json]
  --param_file <PARAM_FILE>  path to save the output for the paramter mappings in cloudformation [Default: keyparams.json]
  --aws_region <AWS_REGION>  AWS region to generate keys for [Default: us-west-2]
  --delete_files             Indicates that files should be deleted once cleanup process is completed

'''
import boto.ec2
import json
import os
from docopt import docopt
import string
import random

arguments = docopt(__doc__, version='demokeys 0.1')

print ''
print '-- Connecting to AWS in region ' + arguments['--aws_region']
conn = boto.ec2.connect_to_region(arguments['--aws_region'])
print '   Connected to AWS API'
print ''

if arguments['create']:

    print '-- Creating keys for bastion and other ec2 instances'
    keys = {}
    key_parameters = {}

    keytypes = []

    print '   Generating ec2 key names' 
    for keytype in ['bastionEc2Key', 'ec2Key']:
        unique_key = keytype + '-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        keytypes.append(unique_key)
        key_parameters[keytype] = unique_key
        print '     Key name for ' + keytype + ' set to ' + unique_key
    print ''

    print '   Creating EC2 keys in ' + arguments['--aws_region']
    for keytype in keytypes:
        keypair = conn.create_key_pair(key_name=keytype)
        keys[keytype] = keypair.material
        print '    ' + keytype + ' created'
    print ''

    with open(arguments['--key_file'], 'w') as key_file:
        print '   Writing key file with private keys to ' + arguments['--key_file']
        key_file.write(json.dumps(keys))

    with open(arguments['--param_file'], 'w') as param_file:
        print '   Writing CloudFormation parameter file to ' + arguments['--param_file']
        param_file.write(json.dumps(key_parameters))

    print ''
    print 'Key creation process complete'

elif arguments['cleanup']:
    with open(arguments['--key_file'], 'r') as key_file: 
        json_data=key_file.read()

    key_data = json.loads(json_data)

    print '-- Cleaning up keys'
    print ''
    for key in key_data.keys(): 
        try:
            print '   ## Deleting key for ' + key
            conn.delete_key_pair(key_name=key)
            print '     ++ key deleted: ' + key
        except:
            print '     ** Key not found'

    if arguments['--delete_files']:
        print ''
        print '   ## Deleting key file'
        os.remove(arguments['--key_file'])
        print '     ++ Key file deleted'

    print ''
    print 'Cleanup Complete'

print ''