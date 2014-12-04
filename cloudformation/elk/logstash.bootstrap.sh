#!/bin/bash
#~LOGSTASH_DOWNLOAD=
#~LOGGING_QUEUE_NAME=
#~LOGGING_QUEUE_REGION=
#~ELASTICSEARCH_ELB_DNS_NAME=
#~ELASTICSEARCH_PORT=9200
#~INDEXER_OUTPUT_FLUSH_SIZE=500
#~LOGGING_QUEUE_THREADS=20
#~FILTER_FILE_ADDRESSES

LOGSTASH_CONF_DIR=/etc/logstash/conf.d
LOGSTASH_CONF=$LOGSTASH_CONF_DIR/logstash.conf

mkdir -p $LOGSTASH_CONF_DIR

sed -i "s/REPLACEQUEUENAME/$LOGGING_QUEUE_NAME/g" /etc/logstash/conf.d/logstash.conf
sed -i "s/REPLACEQUEUEREGION/$LOGGING_QUEUE_REGION/g" /etc/logstash/conf.d/logstash.conf
sed -i "s/REPLACEELASTICSEARCHHOST/$ELASTICSEARCH_ELB_DNS_NAME/g" /etc/logstashconf.d/logstash.conf

sed -i 's/setuid logstash/setuid root/g' /etc/init/logstash.conf
sed -i 's/setgid logstash/setgid root/g' /etc/init/logstash.conf
sed -i 's/\# Defaults/GEM_HOME=\/opt\/logstash\/vendor\/bundle\/jruby\/1.9/g' /etc/init/logstash.conf

service logstash restart