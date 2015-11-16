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
yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
yum -y install docker-engine git python-pip

# Start services
systemctl start docker

# Fetch and install pip packages
sudo -u vagrant git clone https://github.com/openstack/kolla ~vagrant/kolla
pip install ~vagrant/kolla
pip install ~vagrant/kolla-mesos

# Copy configuration
cp -r ~vagrant/kolla/etc/kolla/ /etc/kolla
