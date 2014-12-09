#!/bin/bash
sudo apt-get install -y default-jre-headless
wget https://s3-us-west-2.amazonaws.com/ecs-na-public/elk/logstash-contrib_1.4.2-1-efd53ef_all.deb -O /tmp/contrib.deb --quiet
wget https://s3-us-west-2.amazonaws.com/ecs-na-public/elk/logstash_1.4.2-1-2c0f5a1_all.deb -O /tmp/logstash.deb --quiet
sudo dpkg --install /tmp/logstash.deb
sudo dpkg --install /tmp/contrib.deb
