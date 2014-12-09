#!/bin/bash
if [ -f /vagrant/.boto.cfg ];
then
	sudo cp /vagrant/.boto.cfg /etc/boto.cfg
	sudo chmod +4 /etc/boto.cfg
fi

if [ -f /vagrant/.tower.license ];
then 
	sudo mkdir -p /etc/awx
	sudo chown awx:awx /etc/awx
	sudo chmod 770 /etc/awx -R
	sudo cp /vagrant/.tower.license /etc/awx/license
	sudo chown awx:awx /etc/awx/license
	sudo chmod 400 /etc/awx/license
fi