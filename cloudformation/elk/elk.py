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
                es_layer['elb'], 
                arg_dict.get('elk', {}))

        indexer_layer = self.add_indexer_layer(security_groups['logstash']['instance'], 
                logging_queue,
                es_layer['elb'],
                arg_dict.get('elk', {}))

        scheduler_layer = self.add_scheduler_layer(security_groups['scheduler']['instance'], 
                es_layer['elb'], 
                self.utility_bucket,
                arg_dict.get('elk', {}))

        log_shipper_policies = [iam.Policy(
                            PolicyName='sqsWrite', 
                            PolicyDocument={
                                "Statement": [{
                                    "Effect" : "Allow", 
                                    "Action" : ["sqs:ChangeMessageVisibility","sqs:ChangeMessageVisibilityBatch","sqs:GetQueueAttributes","sqs:GetQueueUrl","sqs:ListQueues","sqs:SendMessage","sqs:SendMessageBatch"], 
                                    "Resource" : [GetAtt(logging_queue,'Arn')]}]})]

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

        self.register_elb_to_dns(kibana_layer['elb'], 'kibana', arg_dict.get('elk', {}))

    def add_security_groups(self, elk_args):
        security_groups = {'elasticsearch':{}, 'kibana':{}, 'logstash':{}, 'scheduler':{}}
        if 'bastionSecurityGroup' in self.template.resources:
            bastion_host_security_group = self.tempalate.resources['bastionSecurityGroup']
        else: 
            bastion_host_security_group = self.template.add_parameter(Parameter('bastionSecurityGroup', 
                Description='ID of the Bastion Host security group.', 
                Type='String'))

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

        if bastion_host_security_group != None:
            self.create_reciprocal_sg(bastion_host_security_group, 'bastion', security_groups['elasticsearch']['elb'], 'elasticsearchElb', elk_args.get('elk_http_port', '9200'))
        
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
            elasticsearch_elb,
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
        logstash_deb_package = self.template.add_parameter(Parameter('logstashIndexerInstallDeb', 
                Type='String', 
                Default=indexer_args.get('indexer_deb_url','https://s3-us-west-2.amazonaws.com/dualspark-binary-cache/elk/logstash_1.4.2-1-2c0f5a1_all.deb'), 
                Description='Location from which to download the Logstash debian package for installation on the indexer layer'))

        if int(indexer_args.get('min_size', 1)) > int(indexer_args.get('max_size', 20)):
            raise RuntimeError('Cannot assign a value for indexer_min_size that is larger than indexer_max_size. Values were set to min of ' + str(indexer_args.get('indexer_min_size', 1)) + ' and a max of ' + str(indexer_args.get('indexer_max_size', 20)) + '.')

        logstash_max_cluster_size = self.template.add_parameter(Parameter('logstashIndexerMaxClusterSize', 
                Type='Number', 
                MinValue=int(indexer_args.get('indexer_min_size', 1)), 
                MaxValue=int(indexer_args.get('indexer_max_size', 20)), 
                Default=str(indexer_args.get('_indexermax_size', 20)),
                Description='Maximum size the indexer cluster will scale up to', 
                ConstraintDescription='Logstash indexer size must be at least ' + str(indexer_args.get('indexer_min_size', 20)) + ' and no larger than ' + str(indexer_args.get('indexer_max_size', 20))))

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
        
        filter_file_addresses = self.template.add_parameter(Parameter('logstashIndexerGrokFiles', 
                Type='String', 
                Default=indexer_args.get('indexer_grok_address_default', 'https://s3-us-west-2.amazonaws.com/pmdevops/demo/elasticsearch/demogrok.txt'), 
                Description='Comma separated collection of URLs to use to get grok patterns for Logstash parsing of log messgaes'))
        
        indexer_vars = []
        indexer_vars.append(Join('=', ['LOGGING_QUEUE_NAME', GetAtt(logging_queue, 'QueueName')]))
        indexer_vars.append(Join('=', ['LOGGING_QUEUE_REGION', Ref('AWS::Region')]))
        indexer_vars.append(Join('=', ['ELASTICSEARCH_ELB_DNS_NAME', GetAtt(elasticsearch_elb, 'DNSName')]))
        indexer_vars.append(Join('=', ['ELASTICSEARCH_PORT', indexer_args.get('elasticsearch_port', '9200')]))
        indexer_vars.append(Join('=', ['INDEXER_OUTPUT_FLUSH_SIZE', indexer_args.get('indexer_output_flush_size', '500')]))
        indexer_vars.append(Join('=', ['LOGGING_QUEUE_THREADS', indexer_args.get('indexer_queue_threds', '40')]))

        iam_profile = self.create_instance_profile('logstashIndexer', indexer_policies)
        bootstrap_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'logstash.bootstrap.sh')

        indexer_asg = self.create_asg('logstashIndexer', 
                instance_profile=iam_profile, 
                ami_name='ubuntuElkLogstash',
                instance_type=indexer_args.get('indexer_instance_type_default', 'c3.large'),
                user_data=self.build_bootstrap([bootstrap_file], indexer_vars), 
                security_groups=[instance_sg, self.common_security_group], 
                min_size=int(indexer_args.get('indexer_min_size',1)), 
                max_size=Ref(logstash_max_cluster_size), 
                instance_monitoring=True,  
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
            utility_bucket, 
            scheduler_args):
        '''
        Method creates a single scheduler instance that manages running api-driven tasks via HTTP for Elasticsearch on a scheduler
        @param instance_sg [Troposphere.ec2.SecurityGroup] Object reference to the instance-level security group for instances created in this layer
        @scheduler_args [dict] collection of configuration values for the cloudformation objects within this layer
        @configarg instance_type_default [string] AWS EC2 Instance Type to be set as the default for the schedulerInstanceType parameter
        ''' 
        iam_profile = self.create_instance_profile('scheduler')

        es_snapshot_name = self.template.add_parameter(Parameter('elasticsearchSnapshotName', 
                Default='ElasticsearchBackup', 
                Type='String', 
                MinLength=4, 
                MaxLength=32, 
                Description='Name to use when creating the Elasticsearch snapshot for backups',
                ConstraintDescription='must be at least 4 characters and no more than 32.'))

        snapshot_key_name_prefix = self.template.add_parameter(Parameter('elasticsearchSnapshotKeyNamePrefix', 
                Default='backup/elasticsearch', 
                Type='String', 
                MinLength=2, 
                MaxLength=128, 
                Description='S3 Key name prefix to apply to the Elasticsearch snapshot', 
                ConstraintDescription='must be at least 2 characters and no more than 128.'))

        snapsoht_frequency = self.template.add_parameter(Parameter('elasticsearchSnapshotFrequency' ,
                Default='60', 
                Type='Number', 
                MinValue=5, 
                MaxValue=60, 
                Description='Interval in minutes to run the elasticsearch snapshot process', 
                ConstraintDescription='must be at least 5 and no more than 60.'))

        scheduler_vars = []
        scheduler_vars.append(Join('=', ['ELASTICSEARCH_ELB_DNS_NAME', GetAtt(elasticsearch_elb, 'DNSName')]))
        scheduler_vars.append(Join('=', ['BACKUP_REPO_NAME', Ref(es_snapshot_name)]))
        scheduler_vars.append(Join('=', ['BUCKET_NAME', Ref(utility_bucket)]))
        scheduler_vars.append(Join('=', ['BUCKET_REGION', Ref('AWS::Region')]))
        scheduler_vars.append(Join('=', ['KEY_NAME_PREFIX', Ref(snapshot_key_name_prefix)]))
        snapshot_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'elasticsearch.snapshot.py')

        scheduler_extra = []
        scheduler_extra.append('cat > /opt/elk_scheduler/elasticsearch.snapshot.py << EOF')
        for line in self.get_file_contents(snapshot_file):
            scheduler_extra.append(line)
        scheduler_extra.append('EOF')
        scheduler_extra.append('chmod +x /opt/elk_scheduler/elasticsearch.snapshot.py')
        scheduler_extra.append(Join('', ['echo "*/', Ref(snapsoht_frequency), ' * * * * root python /opt/elk_scheduler/elasticsearch.snapshot.py create $ELASTICSEARCH_ELB_DNS_NAME --repo_name $BACKUP_REPO_NAME --bucket_name $BUCKET_NAME --bucket_region $BUCKET_REGION --key_name_prefix $KEY_NAME_PREFIX" >> /etc/crontab']))
        bootstrap_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scheduler.bootstrap.sh')

        scheduler_asg = self.create_asg('scheduler', 
            instance_profile=iam_profile, 
            instance_type=scheduler_args.get('scheduler_instance_type_default', 't1.micro'),
            user_data=self.build_bootstrap([bootstrap_file], scheduler_vars, scheduler_extra), 
            security_groups=[instance_sg, self.common_security_group], 
            min_size=1, 
            max_size=1, 
            instance_monitoring=True, 
            root_volume_type=scheduler_args.get('root_volume_type', 'gp2'),
            include_ephemerals=False)

    def add_kibana_layer(self, instance_sg, 
            elb_sg,
            logging_queue,
            backup_bucket,
            elasticsearch_elb, 
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
        kibana_download_package = self.template.add_parameter(Parameter('kibanaInstallTgz', 
                Default=kibana_args.get('kibana_install_tgz_url','https://s3-us-west-2.amazonaws.com/dualspark-binary-cache/elk/kibana-3.1.0.tar.gz'),  
                Type='String',
                Description='Address from which to download the Kibana tgz file to unpack and install'))

        kibana_password = self.template.add_parameter(Parameter('kibanaAccessPassword',  
                Type='String',
                Default='P@ssword!', 
                Description='Password to use when accessing the front end of Kibana',
                NoEcho=True, 
                MinLength=4, 
                MaxLength=20, 
                ConstraintDescription='Password must be at least 4 characters and no more than 20.'))

        kibana_vars = []
        kibana_vars.append(Join('=', ['KIBANA_PASSWORD', Ref(kibana_password)]))
        kibana_vars.append(Join('=', ['KIBANA_URL', Ref(kibana_download_package)]))
        kibana_vars.append(Join('=', ['ELASTICSEARCH_ELB_DNS_NAME', GetAtt(elasticsearch_elb, 'DNSName')]))
        kibana_vars.append(Join('=', ['ELASTICSEARCH_BACKUP_BUCKET', Ref(backup_bucket)]))

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
        bootstrap_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'kibana.bootstrap.sh')

        kibana_asg = self.create_asg('kibana', 
                instance_profile=iam_profile, 
                instance_type=kibana_args.get('kibana_instance_type_default', 't1.micro'),
                user_data=self.build_bootstrap([bootstrap_file], kibana_vars), 
                security_groups=[instance_sg, self.common_security_group], 
                min_size=kibana_args.get('kibana_min_size', 1), 
                max_size=kibana_args.get('kibana_max_size', 4), 
                root_volume_type=kibana_args.get('root_volume_type', 'gp2'),
                instance_monitoring=True, 
                load_balancer=kibana_elb, 
                include_ephemerals=False)

        self.template.add_output(Output('elasticsearchHQDashboard', 
                Value=Join('', ['http://', GetAtt(kibana_elb, 'DNSName'), '/elasticsearch/_plugin/HQ/index.html']), 
                Description='Direct url to Elasticsearch HQ plugin (if installed) to show cluster health information via the ElasticsearchHQ project.'))

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
        es_plugins = self.template.add_parameter(Parameter('elasticsearchPlugins',  
                Type='String',
                Default=es_config.get('elasticsearch_default_plugins', 'elasticsearch/elasticsearch-cloud-aws/2.1.1,royrusso/elasticsearch-HQ'), 
                Description='Comma separated list of Elasticsearch plugins to install. Note that cloud-aws is reqired for AWS cluster discovery'))
        
        es_deb_package = self.template.add_parameter(Parameter('elasticsearchInstallDeb',  
                Type='String',
                Default=es_config.get('elasticsearch_install_deb_url','https://s3-us-west-2.amazonaws.com/dualspark-binary-cache/elk/elasticsearch-1.3.2.deb'),
                Description='Address from which to download the Elasticsearch debian package for installing the service itself'))

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

        es_vars = []
        es_vars.append(Join('=', ['ES_DOWNLOAD', Ref(es_deb_package)]))
        es_vars.append(Join('=', ['ES_PLUGINS', Ref(es_plugins)]))
        es_vars.append(Join('=', ['ES_CLUSTER_NAME', Ref(es_cluster_name)]))
        es_vars.append(Join('=', ['ES_TAG_NAME', es_config.get('elasticsearch_discovery_tag_name','InstanceRole')]))
        es_vars.append(Join('=', ['ES_TAG_VALUE', es_config.get('elasticsearch_discovery_tag_value','Elasticsearch')]))

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

        es_tags = [autoscaling.Tag(es_config.get('elasticsearch_discovery_tag_name','InstanceRole'), es_config.get('elasticsearch_discovery_tag_value','Elasticsearch'), True)]
        bootstrap_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'elasticsearch.bootstrap.sh')

        #                ebs_data_volumes=[{'size':'200', 'type': 'gp2', 'delete_on_termination': False},{'size':'200', 'type': 'gp2', 'delete_on_termination': False},{'size':'200', 'type': 'gp2', 'delete_on_termination': False}],

        es_asg = self.create_asg('elasticsearch', 
                instance_profile=iam_profile, 
                instance_type=es_config.get('elasticsearch_instance_type_default', 'c3.large'),
                user_data=self.build_bootstrap([bootstrap_file], es_vars), 
                security_groups=[instance_sg, self.common_security_group], 
                min_size=str(es_config.get('elasticsearch_cluster_size_default', 5)), 
                max_size=str(es_config.get('elasticsearch_cluster_size_default', 5)), 
                root_volume_type=es_config.get('root_volume_type', 'gp2'),
                instance_monitoring=True, 
                custom_tags=es_tags, 
                load_balancer=es_elb)

        return {'elb': es_elb, 'asg': es_asg}

if __name__ == '__main__':
    import json
    test = Elk({})
    print test.template.to_json()
