#!/usr/bin/env python
'''Base Environment Generator 

This class and command line tool is intended to simplify creating consistent networks from region to region with a good ability to configure a number of pertinent configuration-level options.  

Usage:
    elasticsearch.snapshot.py (-h | --help)
    elasticsearch.snapshot.py --version
    elasticsearch.snapshot.py create <ES_ENDPOINT> --repo_name <REPO_NAME> 
                              [--bucket_name <BUCKET_NAME>] [--bucket_region <BUCKET_REGION>] 
                              [--key_name_prefix <KEY_NAME_PREFIX>] [--indices <INDICES>]
                              [--streams <STREAMS>] [--snapshot_id <SNAPSHOT_ID>]
    elasticsearch.snapshot.py restore <ES_ENDPOINT> --repo_name <REPO_NAME> --snapshot_id <SNAPSHOT_ID>
                              [--bucket_name <BUCKET_NAME>] [--bucket_region <BUCKET_REGION>] 
                              [--key_name_prefix <KEY_NAME_PREFIX>] [--indices <INDICES>]
                              [--streams <STREAMS>] 


Options:
    -h --help                           Show this screen
    --version                           Show version
    --repo_name <REPO_NAME>             Name of the Elasticsearch repository to create or use
    --bucket_name <BUCKET_NAME>         name of the S3 bucket to use for storing snapshots in S3
    --bucket_region <BUCKET_REGION>     name of the AWS region where the snapshot bucket is deployed to [Default: us-east-1]
    --key_name_prefix <KEY_NAME_PREFIX> s3 key name prefix to prepend to the s3 path where the repository should be placed if it does not exist [Default: backups/elasticsearch/]
    --indices <INDICES>                 set, list or identifier for which indices to take action on [Default: *]
    --streams <STREAMS>                 Number of concurrent streams to use when performing snapshots [Default: 20]
    --snapshot_id <SNAPSHOT_ID>         Optional name to assign to the snapshot being created or restored.
'''
import requests
from docopt import docopt
import json
from datetime import datetime

args = docopt(__doc__, version='ElasticsearchSnapshot 1.0')

print args

snapshot = requests.get('http://' + args['<ES_ENDPOINT>'] + ':9200/_snapshot')
if args['--repo_name'] not in snapshot.json(): 
    snapshot_data = {"type" : "s3", 
                     "settings": {
                        "bucket" : args['--bucket_name'], 
                        "region" : args['--bucket_region'], 
                        "base_path": args['--key_name_prefix'], 
                        "concurrent_streams": args['--streams']}}
    snapshot_create = requests.put('http://' + args['<ES_ENDPOINT>'] + ':9200/_snapshot/' + args['--repo_name'], 
            data=json.dumps(snapshot_data))
    if snapshot_create.status_code != 200:
        raise RuntimeError('Creation of snapshot repository returned code ' + str(snapshot_request.status_code) + '. Unable to create the Elasticsearch snapshot repo in S3 with error: ' + snapshot_create.text)

if args['create']:
    if args['--snapshot_id']:
        snapshot_id = args['--snapshot_id']
    else:
        snapshot_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    snapshot_request = requests.put('http://' + args['<ES_ENDPOINT>'] + ':9200/_snapshot/' + args['--repo_name'] + '/' + snapshot_id)

    if snapshot_request.status_code not in [200, 202]: 
        raise RuntimeError('Creation of snapshot returned code ' + str(snapshot_request.status_code) + ' with message ' + snapshot_request.text)
    else:
        print 'Snapshot ' + snapshot_id + ' created.'
elif args['restore']:
    restore_data = {'indices' : args['indices'], 
                    'ignore_unavailable': True, 
                    'ignore_global_state': True}
    restore_request = requests.post('http://' + args['<ES_ENDPOINT>'] + ':9200/_snapshot/' + args['--repo_name'] + '/' + args['--snapshot_id'], data=restore_data)

    if restore_request.status_code not in [200, 202]: 
        raise RuntimeError('Restore call returned code ' + str(restore_request.status_code) + ' with message ' + snapshot_request.text)
    else:
        print 'Snapshot restore of ' + args['--snapshot_id'] + ' has started.'
else:
    print 'Not creating or restoring'

print 'Process complete'
