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
yum -y install docker-engine epel-release git python-pip vim-enhanced

# Start services
systemctl enable docker
systemctl start docker

# Fetch and install pip packages
sudo -u vagrant git clone https://github.com/openstack/kolla ~vagrant/kolla
pip install ~vagrant/kolla
pip install ~vagrant/kolla-mesos

# Copy configuration
cp -r ~vagrant/kolla-mesos/etc/kolla-mesos/ /etc/kolla-mesos
