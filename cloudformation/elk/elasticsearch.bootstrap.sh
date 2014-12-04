#!/bin/bash
#~ES_CLUSTER_NAME=ElkDemo
#~ES_DOWNLOAD=https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-1.1.1.deb
#~ES_PLUGINS=elasticsearch/elasticsearch-cloud-aws/2.1.1,karmi/elasticsearch-paramedic
#~ES_TAG_NAME=InstanceRole
#~ES_TAG_VALUE=Elasticsearc
MNT_TEST=$(df | grep /mnt)
if [ -n "$MNT_TEST" ]; then umount /mnt; fi
sed -i '/\/dev\/xvdb/d' /etc/fstab
mkfs.ext4 /dev/xvdb 
mkfs.ext4 /dev/xvdc
mkdir -p /mnt/xvdb
mkdir -p /mnt/xvdc
echo '/dev/xvdb /mnt/xvdb   ext4    defaults,nobootwait,comment=cloudconfig 0   2' >> /etc/fstab
echo '/dev/xvdc /mnt/xvdc   ext4    defaults,nobootwait,comment=cloudconfig 0   2' >> /etc/fstab
mount -a 
mkdir -p /mnt/xvdb/elasticsearch
mkdir -p /mnt/xvdc/elasticsearch
apt-get -y update 
apt-get install openjdk-7-jre python-pip jq -y --force-yes
wget $ES_DOWNLOAD -O /tmp/elasticsearch.deb
dpkg -i /tmp/elasticsearch.deb
chown elasticsearch:elasticsearch /mnt/xvdb/elasticsearch -R
chown elasticsearch:elasticsearch /mnt/xvdc/elasticsearch -R
INSTANCE_INFO=$(curl http://169.254.169.254/latest/dynamic/instance-identity/document/)
AWS_REGION=$(echo $INSTANCE_INFO | jq --raw-output '.region')
AWS_AZ=$(echo $INSTANCE_INFO | jq --raw-output '.availabilityZone')
AWS_INSTANCE_ID=$(echo $INSTANCE_INFO | jq --raw-output '.instanceId')

cat > /etc/elasticsearch/elasticsearch.yml << EOF
bootstrap:
  mlockall: true
cloud:
  aws.region: $AWS_REGION
cluster:
  name: $ES_CLUSTER_NAME
node:
  name: $AWS_INSTANCE_ID
  datacenter: $AWS_AZ
discovery:
  type: ec2
  ec2.tag.$ES_TAG_NAME: $ES_TAG_VALUE
  zen.ping.multicast.enabled: false
index:
  number_of_replicas: 2
  number_of_shards: 10
path:
  data: /mnt/xvdb/elasticsearch,/mnt/xvdc/elasticsearch
  logs: /var/log/elasticsearch
EOF

IFS=',' read -ra PLUGIN <<< "$ES_PLUGINS"
for i in "${PLUGIN[@]}"; do 
    /usr/share/elasticsearch/bin/plugin -install $i
done

update-rc.d elasticsearch defaults 95 10
sleep .$[ ( $RANDOM % 100 ) + 1 ]s

sudo service elasticsearch restart

exit 0
