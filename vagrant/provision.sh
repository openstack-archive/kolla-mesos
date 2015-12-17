#!/bin/bash

# Disable SELinux
setenforce 0

# Install system packages
cat >/etc/yum.repos.d/docker.repo <<-EOF
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/7
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF
yum -y install docker-engine epel-release git python-devel vim-enhanced
yum -y install python-pip
yum -y groupinstall "Development Tools"
yum clean

# Start services
systemctl enable docker
systemctl start docker

# Fetch and install pip packages
pip install tox
sudo -u vagrant git clone https://github.com/openstack/kolla ~vagrant/kolla
pip install ~vagrant/kolla
pip install ~vagrant/kolla-mesos

# Generate and copy configuration
sudo -u vagrant bash -c "cd ~vagrant/kolla-mesos && tox -e genconfig"
mkdir -p /etc/kolla-mesos
cp -r ~vagrant/kolla/etc/kolla/ /etc/kolla
cp ~vagrant/kolla-mesos/etc/kolla-mesos.conf.sample /etc/kolla-mesos/kolla-mesos.conf

# Change network settings
# TODO(nihilifer): Change kolla_internal_address when loadbalancing will be implemented.
HOST_IP=$(ip addr show eth1 | grep -Po 'inet \K[\d.]+')
sed -i -r "s,^[# ]*kolla_internal_address:.+$,kolla_internal_address: \"$HOST_IP\"," /etc/kolla/globals.yml
sed -i -r "s,^[# ]*network_interface:.+$,network_interface: \"eth1\"," /etc/kolla/globals.yml
sed -i -r "s,^[# ]*neutron_external_interface:.+$,neutron_external_interface: \"eth2\"," /etc/kolla/globals.yml
