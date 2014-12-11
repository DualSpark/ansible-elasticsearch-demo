# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = '2'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  if Vagrant.has_plugin?('landrush')
    config.landrush.enabled = true
    config.landrush.tld = 'dev'
    config.landrush.guest_redirect_dns = false
  end

  config.vm.define 'tower' do |tower|
    tower.vm.box = 'matyunin/centos7'

    if Vagrant.has_plugin?('landrush')
      tower.vm.network 'private_network', type: 'dhcp'
    else
      tower.vm.network 'private_network', ip: '10.42.0.10'
    end

    tower.vm.hostname = 'tower.vagrant.dev'
    tower.vm.provider 'virtualbox' do |vb|
      vb.customize ['modifyvm', :id, '--memory', '2048']
    end

    tower.vm.provision 'shell', path: 'tower.configs.sh'
    
    tower.vm.provision 'ansible' do |ansible|
      ansible.playbook = 'tower.yml'
      ansible.verbose = 'v'
      ansible.sudo = 'true'
      ansible.sudo_user = 'root'
      ansible.host_key_checking = 'false'
    end

    tower.vm.provision 'shell', inline: 'sudo chown awx:awx /etc/awx/license'
    tower.vm.provision 'shell', inline: 'sudo chmod 400 /etc/awx/license'
  end

  config.vm.define 'elk' do |elk|
    elk.vm.box = 'ubuntu1404lts'
    elk.vm.box_url = 'https://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box'

    if Vagrant.has_plugin?('landrush')
      elk.vm.network 'private_network', type: 'dhcp'
    else
      elk.vm.network 'private_network', ip: '10.42.0.20'
    end

    elk.vm.hostname = 'elk.vagrant.dev'
  end

end