#!/usr/env/python
'''
cfgenerator.py

Usage: 
    cfgenerator.py build [<config_file>] [--debug] [--output_file <OUTPUT_FILE>]
                         [--aws_region <AWS_REGION>] [--s3_bucket <S3_BUCKET>]

Options: 
  -h --help                     Show this screen.
  -v --version                  Show version.
  --debug                       Prints parent template to console out [Default: 0]
  --output_file <OUTPUT_FILE>   Destination to print the output file to (if desired) [Default: elkenvironment.debug.template]
  --aws_region <AWS_REGION>     Override to configuration arguments to set region by command line for deployment
  --s3_bucket <S3_BUCKET>       Override to configuration arguments to set s3 bucket to upload templates to 
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
                 arg_dict, 
                 aws_region = None, 
                 bucket_name = None):
        '''
        Method initializes the DevDeploy class and composes the CloudFormation template to deploy the solution 
        @param arg_dict [dict] collection of keyword arguments for this class implementation
        '''
        NetworkBase.__init__(self, arg_dict)
        
        if aws_region != None and 'boto' in arg_dict: 
            arg_dict['boto']['region'] = aws_region

        if bucket_name != None and 'template' in arg_dict: 
            arg_dict['template']['s3_bucket'] = bucket_name

        elk_tier = Elk(arg_dict)
        elk_tier = self.add_child_template('elk', elk_tier)
        self.add_bastion(elk_tier, arg_dict.get('bastion', {}))

    def add_bastion(self, 
            elk_tier,
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


        bastion_security_group = self.template.add_resource(ec2.SecurityGroup('bastionSecurityGroup', 
                VpcId=Ref(self.vpc), 
                GroupDescription='Security group allowing ingress via SSH to this instance along with other standard accessbility port rules', 
                SecurityGroupIngress=[ec2.SecurityGroupRule(
                        FromPort='22', 
                        ToPort='22', 
                        IpProtocol='tcp', 
                        CidrIp='0.0.0.0/0')],
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


        log_queue_arn = Join('', ['arn:aws:sqs:', GetAtt(elk_tier, 'Outputs.logShipperQueueRegion') ,':', Ref('AWS::AccountId'),':', GetAtt(elk_tier, 'Outputs.logShipperQueueName')])

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

        ec2_key = self.template.add_parameter(Parameter('bastionEc2Key', 
            Type='String', 
            Default=bastion_conf.get('bastion_key_default', 'bastionEc2Key'),
            Description='EC2 key to use when deploying the bastion instance'))

        self.template.add_resource(ec2.Instance('bastionInstance',
            IamInstanceProfile=Ref(iam_profile), 
            ImageId=FindInMap('RegionMap', Ref('AWS::Region'), 'ubuntu1404LtsAmiId'), 
            InstanceType=Ref(instance_type), 
            KeyName=Ref(ec2_key),
            Tags=[ec2.Tag('ansible_group', 'bastion')],
            NetworkInterfaces=[ec2.NetworkInterfaceProperty(
                DeviceIndex='0', 
                AssociatePublicIpAddress=True, 
                SubnetId=Ref(self.local_subnets['public']['0']))]
            ))

if __name__ == '__main__':
    arguments = docopt(__doc__, version='devtools 0.1')
    import json
    with open(arguments.get('<config_file>', 'local_dev_args.json'), 'r') as f:
        cmd_args = json.loads(f.read())
    test = DevDeploy(cmd_args)

    if arguments.get('--debug', False):
        print test.to_json()

    with open(arguments.get('--output_file', 'elkenvironment.debug.template'), 'w') as text_file:
        text_file.write(test.to_json())
