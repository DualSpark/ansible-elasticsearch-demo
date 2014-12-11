#!/usr/env/python
'''
generatekeys.py

Usage: 
    generatekeys.py [--aws_region <AWS_REGION>] [--output_file <OUTPUT_FILE>]

Options: 
  -h --help                     Show this screen.
  -v --version                  Show version.
  --output_file <OUTPUT_FILE>   path to save the output [Default: awskeys.json]
  --aws_region <AWS_REGION>     AWS region to generate keys for [Default: us-west-2]

'''
import boto.ec2
import json
from docopt import docopt
import string
import random

arguments = docopt(__doc__, version='generatekeys 0.1')

conn = boto.ec2.connect_to_region(arguments['--aws_region'])
keys = {}

keytypes = []

for keytype in ['ansibledemo-bastion', 'ansibledemo-instances']:
    keytypes.append(keytype + '-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6)))

for keytype in keytypes:
    keypair = conn.create_key_pair(key_name=keytype)
    keys[keytype] = keypair.material

with open(arguments['--output_file'], 'w') as text_file:
    text_file.write(json.dumps(keys))
