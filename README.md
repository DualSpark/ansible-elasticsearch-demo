Ansible, AWS and Elasticsearch demo
======================================================

## Prerequisites

The following must be installed prior to using this demo:

* [Vagrant](https://www.vagrantup.com/downloads.html) - tested with v1.6.5
* [Virtualbox](https://www.virtualbox.org/wiki/Downloads) - tested with v4.3.20-96996

### Helpful configurations

There are a few very useful Vagrant plugins that might make your life a little easier: 

* [Landrush](https://github.com/phinze/landrush)
* [Vagrant-pristine](https://github.com/fgrehm/vagrant-pristine)

## Configuration for the demo

### Get an Ansible Tower License

Go to the [Ansible website](http://www.ansible.com/license) and grab a license. For the purposes of this demo, a 10-node license is sufficient and that level of license is free and won't expire! 

Take the contents of your license (it's a JSON document) and save it to a file in the root of this repository named: ```.tower.license```. This file will be pulled into Vagrant when Tower is set up to automatically apply the license file and bypass the warning labels related to retrieving and applying a license to Tower.

### Get a set of AWS credentials and create a boto.cfg file

AWS Credentials are used for a handful of things in this demo: 

* First, they're used in the CloudFormation generation process
  * Queries AWS to determine the AZ's available to deploy VPC Subnets to
  * Uploads a CloudFormation template to an S3 bucket (you'll need to supply a bucket for this)
* Next, It's used to deploy the CloudFormation template itself
  * Generates EC2 keys for this deployment so they can be used by Ansible
  * Deploys/launches the CloudFormation template that was generated
  * Note: this will deploy EC2 and other resources and may incur a cost to your account.
* Finally, It's used by Ansible Tower to generate a dynamic inventory

## Resources deployed via CloudFormation

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