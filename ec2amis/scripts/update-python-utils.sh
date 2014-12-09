#!/bin/bash
sudo apt-get update -y
sudo apt-get install -y python-pip software-properties-common libyaml-dev python-dev

if [ -f /tmp/beaver ];
then
	sudo mv /tmp/beaver /etc/init.d/beaver
	sudo chmod +x /etc/init.d/beaver
fi

sudo pip install boto 
sudo pip install awscli 
sudo pip install docopt 
sudo pip install beaver
