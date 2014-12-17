# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = '2'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.define 'tower' do |tower|
    tower.vm.box = 'matyunin/centos7'

    if Vagrant.has_plugin?('landrush')
      config.landrush.enabled = true
      config.landrush.tld = 'dev'
      config.landrush.guest_redirect_dns = false
      tower.vm.hostname = 'tower.vagrant.dev'
      tower.vm.network 'private_network', type: 'dhcp'
    else
      tower.vm.network 'private_network', ip: '10.42.0.10'
    end

    tower.vm.provider 'virtualbox' do |vb|
      vb.customize ['modifyvm', :id, '--memory', '2048']
    end

    tower.vm.provision 'shell', path: 'tower.configs.sh'
    tower.vm.provision 'ansible' do |ansible|
      ansible.playbook = 'tower.yml'
      ansible.verbose = 'vvvv'
      ansible.sudo = 'true'
      ansible.sudo_user = 'root'
      ansible.host_key_checking = 'false'
    end

    tower.vm.provision 'shell', inline: 'sudo chown -R awx:awx /etc/awx'
    tower.vm.provision 'shell', inline: 'sudo chown awx:awx /etc/awx/license'
    tower.vm.provision 'shell', inline: 'sudo chmod 400 /etc/awx/license'
  end

end