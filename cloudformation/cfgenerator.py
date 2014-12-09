#!/usr/env/python
'''
cfgenerator.py

Usage: 
    cfgenerator.py build [<config_file>] [--debug] [--output_file <OUTPUT_FILE>]

Options: 
  -h --help                     Show this screen.
  -v --version                  Show version.
  --debug                       Prints parent template to console out [Default: 0]
  --output_file <OUTPUT_FILE>   Destination to print the output file to (if desired) [Default: devdeploy.debug.template]

'''
from environmentbase.networkbase import NetworkBase
from elk.elk import Elk
import troposphere.ec2 as ec2
import troposphere.rds as rds
import troposphere.s3 as s3
import troposphere.sns as sns
import troposphere.sqs as sqs
import troposphere.route53 as r53
import troposphere.elasticloadbalancing as elb
import os
import troposphere.iam as iam
from troposphere import Join, Ref, FindInMap, Parameter, GetAtt, Base64, Output
from docopt import docopt

class DevDeploy(NetworkBase):
    '''
    Class creates an environment with development tools based on the configuration flags passed in.  
    '''

    assume_role_policy_document = {
                   "Statement": [{
                      "Effect": "Allow",
                      "Principal": {
                         "Service": [ "ec2.amazonaws.com" ]},
                      "Action": [ "sts:AssumeRole" ]}]}

    def __init__(self, 
                 arg_dict):
        '''
        Method initializes the DevDeploy class and composes the CloudFormation template to deploy the solution 
        @param arg_dict [dict] collection of keyword arguments for this class implementation
        '''
        NetworkBase.__init__(self, arg_dict)

        elk_tier = Elk(arg_dict)


    def add_ha_bastion_instance(self, 
            puppet_dns_name,
            environment_name,
            bastion_conf):
        '''
        Creates an HA bastion instance
        '''
        instance_type = self.template.add_parameter(Parameter('bastionInstanceType', 
                Default=bastion_conf.get('instance_type_default', 't1.micro'), 
                AllowedValues=self.strings['valid_instance_types'], 
                Type='String',
                Description='Instance type to use when launching the Bastion host for access to resources that are not publicly exposed', 
                ConstraintDescription=self.strings['valid_instance_type_message']))

        bastion_elb_security_group = self.template.add_resource(ec2.SecurityGroup('bastionElbSecurityGroup', 
                VpcId=Ref(self.vpc), 
                GroupDescription='Security group allowing ingress via SSH to this instance along with other standard accessbility port rules', 
                SecurityGroupIngress=[ec2.SecurityGroupRule(
                        FromPort=bastion_conf.get('public_ssh_port', '2222'), 
                        ToPort=bastion_conf.get('public_ssh_port', '2222'), 
                        IpProtocol='tcp', 
                        CidrIp=Ref(self.template.parameters['remoteAccessLocation']))]))

        bastion_security_group = self.template.add_resource(ec2.SecurityGroup('bastionSecurityGroup', 
                VpcId=Ref(self.vpc), 
                GroupDescription='Security group allowing ingress via SSH to this instance along with other standard accessbility port rules', 
                SecurityGroupIngress=[ec2.SecurityGroupRule(
                        FromPort='22', 
                        ToPort='22', 
                        IpProtocol='tcp', 
                        SourceSecurityGroupId=Ref(bastion_elb_security_group))],
                SecurityGroupEgress=[ec2.SecurityGroupRule(
                        FromPort='22', 
                        ToPort='22', 
                        IpProtocol='tcp', 
                        CidrIp=FindInMap('networkAddresses', 'vpcBase', 'cidr')), 
                    ec2.SecurityGroupRule(
                        FromPort='80', 
                        ToPort='80', 
                        IpProtocol='tcp', 
                        CidrIp='0.0.0.0/0'), 
                    ec2.SecurityGroupRule(
                        FromPort='443', 
                        ToPort='443', 
                        IpProtocol='tcp',
                        CidrIp='0.0.0.0/0')]))

        self.template.add_resource(ec2.SecurityGroupEgress('bastionElbSecurityGroupEgressSSHToInstance', 
                GroupId=Ref(bastion_elb_security_group), 
                DestinationSecurityGroupId=Ref(bastion_security_group), 
                FromPort='22', 
                ToPort='22', 
                IpProtocol='tcp'))

        bastion_elb = self.template.add_resource(elb.LoadBalancer('bastionElb', 
            Subnets=self.subnets['public'], 
            SecurityGroups=[Ref(bastion_elb_security_group)], 
            CrossZone=True,
            AccessLoggingPolicy=elb.AccessLoggingPolicy(
                EmitInterval=5,
                Enabled=True,
                S3BucketName=Ref(self.utility_bucket)),
            HealthCheck=elb.HealthCheck(
                    HealthyThreshold=3, 
                    UnhealthyThreshold=5,
                    Interval=60, 
                    Target=bastion_conf.get('healthcheck_protocol', 'tcp').upper() + ':' + bastion_conf.get('ssh_port', '22') , 
                    Timeout=5), 
            Listeners=[elb.Listener(
                        LoadBalancerPort=bastion_conf.get('public_ssh_port', '2222'), 
                        InstancePort=bastion_conf.get('ssh_port', '22'), 
                        Protocol=bastion_conf.get('elb_protocol', 'tcp').upper())]))

        if 'logShipperQueueName' in self.template.parameters:
            log_queue = self.template.parameters['logShipperQueueName']
        else:
            log_queue = self.template.add_parameter(Parameter('logShipperQueueName', 
                Type='String', 
                Description='Name of the SQS queue used for logging'))

        if 'logShipperQueueRegion' in self.template.parameters:
            log_region = self.template.parameters['logShipperQueueRegion']
        else:
            log_region = self.template.add_parameter(Parameter('logShipperQueueRegion', 
                Type='String', 
                Description='Region of the SQS queue used for logging'))

        log_queue_arn = Join('', ['arn:aws:sqs:', Ref(log_region) ,':', Ref('AWS::AccountId'),':', Ref(log_queue)])

        iam_policies = [iam.Policy(
                            PolicyName='logQueueWrite', 
                            PolicyDocument={
                                "Statement" : [{
                                    "Effect" : "Allow", 
                                    "Action" : ["sqs:SendMessage"], 
                                    "Resource" : [log_queue_arn]}]}), 
                      iam.Policy(
                            PolicyName='logReadQueues', 
                            PolicyDocument={
                                "Statement" : [{
                                    "Effect" : "Allow", 
                                    "Action" : ["sqs:Get*", "sqs:List*"], 
                                    "Resource" :"*"}]}),
                      iam.Policy(
                            PolicyName='cloudWatchPostData', 
                            PolicyDocument={
                                "Statement": [{
                                    "Action": ["cloudwatch:PutMetricData"],
                                    "Effect": "Allow",
                                    "Resource": "*"}]})]

        iam_profile = self.create_instance_profile('bastion', iam_policies)

        bastion_asg = self.create_asg('bastionASG',
                instance_profile=iam_profile,
                ami_name="ubuntuPuppet",
                instance_type=instance_type,
                security_groups=[bastion_security_group], 
                min_size=1, 
                max_size=1, 
                load_balancer={'public': bastion_elb},
                include_ephemerals=False,
                instance_monitoring=bastion_conf.get('instance_monitoring', False))

        return {'elb': bastion_elb, 'asg': bastion_asg}


if __name__ == '__main__':
    arguments = docopt(__doc__, version='devtools 0.1')
    import json
    with open(arguments.get('<config_file>', 'local_dev_args.json'), 'r') as f:
        cmd_args = json.loads(f.read())
    test = DevDeploy(cmd_args)

    if arguments.get('--debug', False):
        print test.to_json()

    with open(arguments.get('--output_file', 'devdeploy.debug.template'), 'w') as text_file:
        text_file.write(test.to_json())