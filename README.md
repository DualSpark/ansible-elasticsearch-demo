Ansible, AWS and Elasticsearch demo
======================================================

## Prerequisites

The following must be installed prior to using this demo:
* [Vagrant](https://www.vagrantup.com/downloads.html) - tested with v1.6.5
* [Virtualbox](https://www.virtualbox.org/wiki/Downloads) - tested with v4.3.20-96996

You will also need AWS credentials to deploy a set of CloudFormation scripts which will crate an Elasticsearch deployment:

* 1 S3 Bucket
* 1 public-facing ELB
* 1 private ELB
* 1 SQS Queue
* 1 VPC with 2 public (/24) and 2 private subnets (/20) containing:
  * 1 bastion host
  * 1 Autoscaling group for Elasticsearch (min: 3, max: 3, desired: 3)
  * 1 Autoscaling group for Logstash Indexers (min: 1, max: 4, desired: 1)
  * 1 Autoscaling group to host Kibana (min: 1, max: 1, desired: 1)
  * 1 Autoscaling group for the Scheduler instance (min: 1, max: 1, desired: 1)

## Running this demo

To start Tower, run the following command from the root of this repository in a terminal: 

```
vagrant up tower
```

## To log into Tower

If you have the Landrush Vagrant plugin installed:

```https://tower.vagrant.dev```


Otherwise, you can use the IP address directly: 

```https://10.42.0.10```

Credentials for logging in the first time are:

* username: admin
* password: password