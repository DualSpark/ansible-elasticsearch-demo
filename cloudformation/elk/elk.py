from troposphere import Join, Ref, FindInMap, Parameter, GetAtt, Base64, Output
import troposphere.s3 as s3
import troposphere.sqs as sqs
import troposphere.autoscaling as autoscaling
import troposphere.ec2 as ec2
import troposphere.iam as iam
import troposphere.elasticloadbalancing as elb
import troposphere.cloudwatch as cloudwatch
from environmentbase.templatebase import TemplateBase
import os

class Elk(TemplateBase):

    def __init__(self, arg_dict):
        TemplateBase.__init__(self, arg_dict)
        self.strings['valid_es_instance_types'] = ["m3.xlarge","m3.2xlarge","m1.large","m1.xlarge","c3.large","c3.xlarge","c3.2xlarge","c3.4xlarge","c3.8xlarge","c1.xlarge","cc2.xlarge","cg1.4xlarge","m2.4xlarge","cr1.8xlarge","i2.2xlarge","i2.4xlarge","hs1.8xlarge", "hi1.4xlarge"]
        self.strings['valid_es_instance_type_message'] = "must be an instance type that supports 2 or more ephemeral volumes."
        logging_queue = self.template.add_resource(sqs.Queue('loggingQueue'))

        file_notification_queue = self.template.add_resource(sqs.Queue('fileTransferQueue'))

        file_transfer_queue = self.template.add_output(Output('fileTransferQueue', 
            Value=Ref(file_notification_queue), 
            Description='Queue for receiving notifications that log files have been dropped.'))

        self.template.add_resource(sqs.QueuePolicy('fileQueuePolicy', 
            PolicyDocument={
                "Statement": [{
                    "Effect": "Allow", 
                    "Principal": {"AWS": "*"}, 
                    "Action" : ["SQS:SendMessage"], 
                    "Resource": GetAtt(file_transfer_queue, 'Arn'), 
                    "Condition": {
                        "StringLike": {
                            "aws:SourceArn" : Join(':', ['arn', 'aws', 's3', Ref('AWS::AccountId'), '*', '*'])}}}]}, 
            Queues=[Ref(file_transfer_queue)]))

        security_groups = self.add_security_groups(arg_dict.get('elk', {}))
        es_layer = self.add_elasticsearch_layer(security_groups['elasticsearch']['instance'], 
                security_groups['elasticsearch']['elb'], 
                logging_queue, 
                self.utility_bucket, 
                arg_dict.get('elk', {}))

        kibana_layer = self.add_kibana_layer(
                security_groups['kibana']['instance'], 
                security_groups['kibana']['elb'], 
                logging_queue, 
                self.utility_bucket, 
                arg_dict.get('elk', {}))

        indexer_layer = self.add_indexer_layer(security_groups['logstash']['instance'], 
                logging_queue,
                arg_dict.get('elk', {}))

        log_shipper_policies = [iam.Policy(
                    PolicyName='sqsWrite', 
                    PolicyDocument={
                        "Statement": [{
                            "Effect" : "Allow", 
                            "Action" : ["sqs:ChangeMessageVisibility","sqs:ChangeMessageVisibilityBatch","sqs:GetQueueAttributes","sqs:GetQueueUrl","sqs:ListQueues","sqs:SendMessage","sqs:SendMessageBatch"], 
                            "Resource" : [GetAtt(logging_queue,'Arn')]}]})]


        scheduler_layer = self.add_scheduler_layer(security_groups['scheduler']['instance'], 
                es_layer['elb'], 
                log_shipper_policies,
                arg_dict.get('elk', {}))

        log_shipper_user = self.template.add_resource(iam.User('logShipperUser', 
                Policies=log_shipper_policies))

        log_shipper_key = self.template.add_resource(iam.AccessKey('logShipperKeys', 
                UserName=Ref(log_shipper_user)))

        self.template.add_output(Output('logShipperAccessKeyId', 
                Value=Ref(log_shipper_key), 
                Description='AWS Access Key ID to use when configuring external log shippers'))

        self.template.add_output(Output('logShipperSecretKeyId', 
                Value=GetAtt(log_shipper_key, 'SecretAccessKey'), 
                Description='AWS Secret Access Key to use when configuring external log shippers'))

        self.template.add_output(Output('logShipperQueueName', 
                Value=GetAtt(logging_queue, 'QueueName'), 
                Description='Name of the SQS queue for log shipping to use when configuring external log shippers to publish to this deployment of Elasticsearch'))

        self.template.add_output(Output('logShipperQueueRegion', 
                Value=Ref('AWS::Region'), 
                Description='Region where the log shipping queue is deployed to use when configuring external log shippers'))

    def add_security_groups(self, elk_args):
        security_groups = {'elasticsearch':{}, 'kibana':{}, 'logstash':{}, 'scheduler':{}}

        #allow SSH in from the virtual private network only
        common_ingress_rules = [
            ec2.SecurityGroupRule(
                FromPort='22', 
                ToPort='22', 
                IpProtocol='tcp', 
                CidrIp=FindInMap('networkAddresses', 'vpcBase', 'cidr'))]

        security_groups['logstash']['instance'] = self.template.add_resource(ec2.SecurityGroup('logstashIndexerInstanceSecurityGroup', 
            GroupDescription='Security group allows egress to Elasticsearch on tcp port 9200 as well as other common rules used in accessing the system', 
            VpcId=Ref(self.vpc_id)))

        security_groups['kibana']['elb'] = self.template.add_resource(ec2.SecurityGroup('kibanaElbSecurityGroup', 
            GroupDescription='Security group allowing public ingress into the elb via http connecting back to an auto scaling group of kibana instances', 
            VpcId=Ref(self.vpc_id), 
            SecurityGroupIngress=[ec2.SecurityGroupRule(
                FromPort=elk_args.get('kibana_port', '80'), 
                ToPort=elk_args.get('kibana_port', '80'), 
                IpProtocol='tcp', 
                CidrIp=elk_args.get('kibana_remote_access_cidr', '0.0.0.0/0'))]))

        security_groups['kibana']['instance'] = self.template.add_resource(ec2.SecurityGroup('kibanaInstanceSecurityGroup', 
            GroupDescription='Security group allows ingress from kibana elb via http as well as other common rules used in accessing the system', 
            VpcId=Ref(self.vpc_id)))

        security_groups['elasticsearch']['elb'] = self.template.add_resource(ec2.SecurityGroup('elasticsearchElbSecurityGroup', 
            GroupDescription='Security group allows ingress to the elb and egress to Elasticsearch only on tcp port 9200', 
            VpcId=Ref(self.vpc_id)))

        security_groups['elasticsearch']['instance'] = self.template.add_resource(ec2.SecurityGroup('elasticsearchInstanceSecurityGroup', 
            GroupDescription='Security group allows ingress from elasticserach elb via http with self-referencing rules for clustering as well as other common rules used in accessing the system', 
            VpcId=Ref(self.vpc_id)))

        security_groups['scheduler']['instance'] = self.template.add_resource(ec2.SecurityGroup('schedulerInstanceSecurityGroup', 
            GroupDescription='Security group allows ingress to Elasticsearch ELB to manage backup snapshots and other scheduled tasks as needed', 
            VpcId=Ref(self.vpc_id)))

        self.create_reciprocal_sg(security_groups['kibana']['elb'], 'kibanaElb', security_groups['kibana']['instance'], 'kibanaInstance', elk_args.get('kibana_port', '80'), elk_args.get('kibana_healthcheck_port', '81'))    
        self.create_reciprocal_sg(security_groups['elasticsearch']['elb'], 'elasticsearchElb', security_groups['elasticsearch']['instance'], 'elasticsearchInstance', elk_args.get('elk_http_port', '9200'))
        self.create_reciprocal_sg(security_groups['kibana']['instance'], 'kibanaInstance', security_groups['elasticsearch']['elb'], 'elasticsearchElb', elk_args.get('elk_http_port', '9200'))
        self.create_reciprocal_sg(security_groups['logstash']['instance'], 'logstashIndexerInstance', security_groups['elasticsearch']['elb'], 'elasticsearchElb', elk_args.get('elk_http_port', '9200'))
        self.create_reciprocal_sg(security_groups['elasticsearch']['instance'], 'elasticsearchInstance', security_groups['elasticsearch']['instance'], 'elasticsearchInstance', elk_args.get('elk_cluster_from_port', '9200'), elk_args.get('elk_cluster_to_port', '9400'))
        self.create_reciprocal_sg(security_groups['scheduler']['instance'], 'schedulerInstance', security_groups['elasticsearch']['elb'], 'elasticsearchElb', elk_args.get('elk_http_port', '9200'))
        return security_groups

    def add_indexer_layer(self, 
            instance_sg,
            logging_queue, 
            indexer_args):
        '''
        Method encapsulates process of creating the resources required for the Logstash indexer layer
        @param instance_sg [Troposphere.ec2.SecurityGroup] Object reference to the instance-level security group created for instances in this layer
        @param logging_queue [Troposphere.sqs.Queue] Reference to the SQS queue to be used as the log transport layer for this deployment
        @param indexer_args [dict] Dictionary of key-value pairs holding optional arguments for this class
        @configarg indexer_min_size [int] minimum size of the auto scaling group deployed for the indexer tier.  
        @configarg indexer_max_size [int] maximum size of the auto scaling group deployed for the indexer tier.  
        @configarg indexer_instance_type_default [string] AWS EC2 Instance Type to use when launching indexer instances
        @configarg low_queue_depth_threshold [int] threshold in terms of the number of messages in the logging queue where the Auto Scaling group will scale down 
        @configarg high_queue_depth_threshold [int] threshold in terms of the number of messages in the logging queue where the Auto Scaling group will scale up 
        @configarg logstash_install_deb_url_default [string] http path to set as the default value for the logstashIndexerInstallDeb CloudFormation property
        '''
        if int(indexer_args.get('min_size', 1)) > int(indexer_args.get('max_size', 4)):
            raise RuntimeError('Cannot assign a value for indexer_min_size that is larger than indexer_max_size. Values were set to min of ' + str(indexer_args.get('indexer_min_size', 1)) + ' and a max of ' + str(indexer_args.get('indexer_max_size', 4)) + '.')

        logstash_max_cluster_size = self.template.add_parameter(Parameter('logstashIndexerMaxClusterSize', 
                Type='Number', 
                MinValue=int(indexer_args.get('indexer_min_size', 1)), 
                MaxValue=int(indexer_args.get('indexer_max_size', 4)), 
                Default=str(indexer_args.get('_indexermax_size', 4)),
                Description='Maximum size the indexer cluster will scale up to', 
                ConstraintDescription='Logstash indexer size must be at least ' + str(indexer_args.get('indexer_min_size', 4)) + ' and no larger than ' + str(indexer_args.get('indexer_max_size', 4))))

        indexer_policies = [iam.Policy(
                            PolicyName='cloudformationRead', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["cloudformation:DescribeStackEvents",
                                                "cloudformation:DescribeStackResource",
                                                "cloudformation:DescribeStackResources",
                                                "cloudformation:DescribeStacks",
                                                "cloudformation:ListStacks",
                                                "cloudformation:ListStackResources"], 
                                    "Resource" : "*"}]}),
                            iam.Policy(
                                PolicyName='SQSWrite', 
                                PolicyDocument = {
                                    "Statement": [{
                                        "Effect": "Allow", 
                                        "Action": ["sqs:*"], 
                                        "Resource": GetAtt(logging_queue, 'Arn')}]})]
        
        iam_profile = self.create_instance_profile('logstashIndexer', indexer_policies)
        indexer_tags = [autoscaling.Tag('ansible_group', 'elk-indexer', True)]

        indexer_asg = self.create_asg('logstashIndexer', 
                instance_profile=iam_profile, 
                ami_name='ubuntu1404LtsAmiId',
                instance_type=indexer_args.get('indexer_instance_type_default', 'c3.large'),
                security_groups=[instance_sg, self.common_security_group], 
                min_size=int(indexer_args.get('indexer_min_size',1)), 
                max_size=Ref(logstash_max_cluster_size), 
                instance_monitoring=True,  
                custom_tags=indexer_tags,
                root_volume_type=indexer_args.get('root_volume_type', 'gp2'),
                include_ephemerals=False)

        scale_up_policy = self.template.add_resource(autoscaling.ScalingPolicy('loggingIndexerScaleUpPolicy', 
                AdjustmentType='ChangeInCapacity', 
                AutoScalingGroupName=Ref(indexer_asg), 
                Cooldown='600', 
                ScalingAdjustment='2'))

        scale_down_policy = self.template.add_resource(autoscaling.ScalingPolicy('loggingIndexerScaleDownPolicy', 
                AdjustmentType='ChangeInCapacity', 
                AutoScalingGroupName=Ref(indexer_asg), 
                Cooldown='600', 
                ScalingAdjustment='-1'))

        high_alarm = self.template.add_resource(cloudwatch.Alarm('loggingIndexerHighAlarm', 
                Namespace='AWS/SQS', 
                MetricName='ApproximateNumberOfMessagesVisible', 
                Dimensions=[cloudwatch.MetricDimension(Name='QueueName', Value=Ref(logging_queue))], 
                Statistic='Sum', 
                AlarmActions=[Ref(scale_up_policy)],
                Period='300', 
                EvaluationPeriods='1', 
                Threshold=str(indexer_args.get('indexer_high_queue_depth_threshold', 10000)), 
                ComparisonOperator='GreaterThanThreshold'))

        low_alarm = self.template.add_resource(cloudwatch.Alarm('loggingIndexerLowAlarm', 
                Namespace='AWS/SQS', 
                MetricName='ApproximateNumberOfMessagesVisible', 
                Dimensions=[cloudwatch.MetricDimension(Name='QueueName', Value=Ref(logging_queue))], 
                Statistic='Sum', 
                AlarmActions=[Ref(scale_down_policy)],
                Period='300', 
                EvaluationPeriods='1', 
                Threshold=str(indexer_args.get('indexer_low_queue_depth_threshold', 1000)), 
                ComparisonOperator='LessThanThreshold'))

    def add_scheduler_layer(self, 
            instance_sg, 
            elasticsearch_elb, 
            scheduler_args):
        '''
        Method creates a single scheduler instance that manages running api-driven tasks via HTTP for Elasticsearch on a scheduler
        @param instance_sg [Troposphere.ec2.SecurityGroup] Object reference to the instance-level security group for instances created in this layer
        @scheduler_args [dict] collection of configuration values for the cloudformation objects within this layer
        @configarg instance_type_default [string] AWS EC2 Instance Type to be set as the default for the schedulerInstanceType parameter
        ''' 
        iam_profile = self.create_instance_profile('scheduler')
        scheduler_tags = [autoscaling.Tag('ansible_group', 'elk-scheduler', True)]

        scheduler_asg = self.create_asg('scheduler', 
            instance_profile=iam_profile, 
            instance_type=scheduler_args.get('scheduler_instance_type_default', 'm1.small'),
            security_groups=[instance_sg, self.common_security_group], 
            min_size=1, 
            max_size=1, 
            ami_name='ubuntu1404LtsAmiId',
            instance_monitoring=True, 
            custom_tags=scheduler_tags,
            root_volume_type=scheduler_args.get('root_volume_type', 'gp2'),
            include_ephemerals=False)

    def add_kibana_layer(self, instance_sg, 
            elb_sg,
            logging_queue,
            backup_bucket,
            kibana_args):
        '''
        Method handles creation of the kibana layer which will surface the kibana front end as well as a proxy directly to Elasticsearch behind a password-protected web server
        @param instance_sg [Troposphere.ec2.SecurityGroup] Object reference to the instance-level security group created for instances in this layer
        @param elb_sg [Troposphere.ec2.SecurityGroup] Object reference to the elb-level security group created for the ELB that sits in front of this layer
        @param logging_queue [Troposphere.sqs.Queue] Object reference to the SQS queue to use for log aggregation transport
        @param backup_bucket [Troposphere.s3.Bucket] Object reference to the S3 bucket to be used for backups/snapshots in Elasticsearch
        @param elasticsearch_elb [Troposphere.elasticloadbalancing.LoadBalancer] internal ELB serving as the front-end for the http service for Elasticsearch
        @configarg kibana_install_tgz_url_default [string] value to set as default for the kibanaInstallTgz parameter indicating where to download the Kibana app from 
        @configarg kibana_instance_type_default [string] AWS EC2 Instance Type to be set as the default_pluginsult for the kibanaInstanceType Parameter
        @configarg kibana_min_size [int] minimum number of instances to be deployed for the Kibana Auto Scaling group
        @configarg kibana_max_size [int] maximum number of instances to be deployed for the Kibana Auto Scaling group
        '''
        kibana_elb = self.template.add_resource(elb.LoadBalancer('kibanaExternalElb', 
                Subnets=self.subnets['public'], 
                SecurityGroups=[Ref(elb_sg)], 
                CrossZone=True,
                AccessLoggingPolicy=elb.AccessLoggingPolicy(
                    EmitInterval=5,
                    Enabled=True,
                    S3BucketName=Ref(self.utility_bucket)),
                HealthCheck=elb.HealthCheck(
                        HealthyThreshold=3, 
                        UnhealthyThreshold=5,
                        Interval=30, 
                        Target='HTTP:81/', 
                        Timeout=5), 
                Listeners=[elb.Listener(
                        LoadBalancerPort='80', 
                        InstancePort='80', 
                        Protocol='HTTP')]))

        kibana_policies = [iam.Policy(
                            PolicyName='sqsWrite', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["sqs:ChangeMessageVisibility","sqs:ChangeMessageVisibilityBatch","sqs:GetQueueAttributes","sqs:GetQueueUrl","sqs:ListQueues","sqs:SendMessage","sqs:SendMessageBatch"], 
                                    "Resource" : [GetAtt(logging_queue,'Arn')]}]}),
                       iam.Policy(
                            PolicyName='s3AllForBackupBucket', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["s3:*"], 
                                    "Resource" : [Join('', ['arn:aws:s3:::', Ref(backup_bucket), "/*"])]
                                }]}),
                       iam.Policy(
                            PolicyName='s3ListAndGetBucket', 
                            PolicyDocument={
                                "Statement" : [{
                                    "Effect" : "Allow", 
                                    "Action" : ["s3:List*", "s3:GetBucket*"], 
                                    "Resource" : "arn:aws:s3:::*"}]})]

        iam_profile = self.create_instance_profile('kibana', kibana_policies)
        kibana_tags = [autoscaling.Tag('ansible_group', 'elk-kibana', True)]

        kibana_asg = self.create_asg('kibana', 
                instance_profile=iam_profile, 
                instance_type=kibana_args.get('kibana_instance_type_default', 't1.micro'),
                security_groups=[instance_sg, self.common_security_group], 
                min_size=kibana_args.get('kibana_min_size', 1), 
                max_size=kibana_args.get('kibana_max_size', 4), 
                ami_name='ubuntu1404LtsAmiId',
                root_volume_type=kibana_args.get('root_volume_type', 'gp2'),
                instance_monitoring=True, 
                custom_tags=kibana_tags,
                load_balancer=Ref(kibana_elb), 
                include_ephemerals=False)

        self.template.add_output(Output('kibanaDashboard', 
                Value=Join('', ['http://', GetAtt(kibana_elb, 'DNSName'), '/index.html']), 
                Description='Direct url to access the kibana front-end dashboard pages.'))

        return {'elb': kibana_elb, 'asg': kibana_asg}

    def add_elasticsearch_layer(self, 
            instance_sg, 
            elb_sg, 
            logging_queue, 
            backup_bucket, 
            es_config):
        '''
        Method encapsulates the resources required to deploy Elasticsearch in a multi-node configuration.  Includes configuration for snapshot backups to S3.
        Returns a dictionary containing object references to the ASG and the ELB created for this layer
        @param instance_sg [Troposphere.ec2.SecurityGroup] Object reference to the instance-level security group created for instances in this layer
        @param elb_sg [Troposphere.ec2.SecurityGroup] Object reference to the elb-level security group created for the ELB that sits in front of this layer
        @param logging_queue [Troposphere.sqs.Queue] object reference to the SQS queue created to manage logs to identify where instance logs should be shipped to for aggregation
        @param backup_bucket [Troposphere.s3.Bucket] object reference to the S3 bucket to be used when performing snapshot operations from within ElasticSearch
        @param es_config [dict] collection of configuration values for the cloudformation objects within this layer
        @configarg install_deb_url_default [string] value to set as default for the elasticsarchInstallDeb parameter indicating where to download the Elasticsearch app from 
        @configarg cluster_size_default [int] value to set as the default for the size of the elasticsearch cluster 
        @configarg discovery_tag_name [string] name of the tag to use for cloud-aws tag-based discovery
        @configarg discovery_tag_value [string] value of the tag to use for cloud-aws tag-based discovery
        @configarg instance_type_default [string] valid EC2 instance type with 2 or more ephemeral drives available
        @configarg default_plugins [string] list of Elasticsearch plugins to set as the default when generating this template
        '''
        es_cluster_name = self.template.add_parameter(Parameter('elasticsearchClusterName', 
                Default=es_config.get('elasticsearch_cluster_name', 'ElkDemo'),  
                Type='String',
                Description='Name to assign to the cluster itself. Used for identifying the whole Elasticsearch cluster together as a group.', 
                MinLength=4, 
                MaxLength=32, 
                ConstraintDescription='Cluster name must be at least 4 and no more than 32 characters long.'))

        es_policies = [iam.Policy(
                            PolicyName='sqsWrite', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["sqs:ChangeMessageVisibility","sqs:ChangeMessageVisibilityBatch","sqs:GetQueueAttributes","sqs:GetQueueUrl","sqs:ListQueues","sqs:SendMessage","sqs:SendMessageBatch"], 
                                    "Resource" : [GetAtt(logging_queue, 'Arn')]}]}),
                       iam.Policy(
                            PolicyName='ec2DescribeAllInstancesInRegion', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" :["ec2:Describe*"], 
                                    "Resource" : "*"}]}),
                       iam.Policy(
                            PolicyName='s3AllForBackupBucket', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["s3:*"], 
                                    "Resource" : [Join('', ['arn:aws:s3:::', Ref(backup_bucket), "/*"])]}]}),
                       iam.Policy(
                            PolicyName='s3ListAndGetBucket', 
                            PolicyDocument={
                                "Statement" : [{
                                    "Effect" : "Allow", 
                                    "Action" : ["s3:List*", "s3:GetBucket*"], 
                                    "Resource" : "arn:aws:s3:::*"}]})]

        iam_profile = self.create_instance_profile('elasticsearch', es_policies)

        es_elb = self.template.add_resource(elb.LoadBalancer('elasticsearchInternalElb', 
                Subnets=self.subnets['private'], 
                SecurityGroups=[Ref(elb_sg)], 
                CrossZone=True,
                AccessLoggingPolicy=elb.AccessLoggingPolicy(
                    EmitInterval=5,
                    Enabled=True,
                    S3BucketName=Ref(self.utility_bucket)),
                HealthCheck=elb.HealthCheck(
                        HealthyThreshold=3, 
                        UnhealthyThreshold=5,
                        Interval=30, 
                        Target='HTTP:9200/', 
                        Timeout=5), 
                Listeners=[elb.Listener(
                        LoadBalancerPort='9200', 
                        InstancePort='9200', 
                        Protocol='HTTP')], 
                Scheme='internal'))

        es_tags = [autoscaling.Tag(es_config.get('elasticsearch_discovery_tag_name','InstanceRole'), es_config.get('elasticsearch_discovery_tag_value','Elasticsearch'), True),
                    autoscaling.Tag('ansible_group', 'elk-elasticsearch', True)]

        es_asg = self.create_asg('elasticsearch', 
                instance_profile=iam_profile, 
                ami_name='ubuntu1404LtsAmiId',
                instance_type=es_config.get('elasticsearch_instance_type_default', 'c3.large'),
                security_groups=[instance_sg, self.common_security_group], 
                min_size=str(es_config.get('elasticsearch_cluster_size_default', 3)), 
                max_size=str(es_config.get('elasticsearch_cluster_size_default', 3)), 
                root_volume_type=es_config.get('root_volume_type', 'gp2'),
                instance_monitoring=True, 
                custom_tags=es_tags, 
                load_balancer=Ref(es_elb))

        return {'elb': es_elb, 'asg': es_asg}

if __name__ == '__main__':
    import json
    test = Elk({})
    print test.template.to_json()
