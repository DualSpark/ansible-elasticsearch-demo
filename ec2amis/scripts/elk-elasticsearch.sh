#!/bin/bash
sudo apt-get install -y default-jre-headless
wget https://s3-us-west-2.amazonaws.com/ecs-na-public/elk/elasticsearch-1.4.1.deb -O /tmp/elasticsearch.deb --quiet
sudo dpkg --install /tmp/elasticsearch.deb
