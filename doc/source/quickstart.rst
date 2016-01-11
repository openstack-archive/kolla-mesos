Development Environment with Vagrant
====================================

This guide describes how to use `Vagrant <http://vagrantup.com>`__ to
assist in developing for Kolla-Mesos.

Vagrant is a tool to assist in scripted creation of virtual machines. Vagrant
takes care of setting up CentOS-based VMs for Kolla-Mesos development, each with
proper hardware like memory amount and number of network interfaces.

Getting Started
---------------

The Vagrant script implements All-in-One (AIO).

Start by downloading and installing the Vagrant package for the distro of
choice. Various downloads can be found at the `Vagrant downloads
<https://www.vagrantup.com/downloads.html>`__.

On Fedora it is as easy as::

    sudo dnf install vagrant ruby-devel

**Note:** Many distros ship outdated versions of Vagrant by default. When in
doubt, always install the latest from the downloads page above.

Next install the hostmanager plugin so all hosts are recorded in /etc/hosts
(inside each vm)::

    vagrant plugin install vagrant-hostmanager

Vagrant supports a wide range of virtualization technologies. This
documentation describes libvirt.

Firstly, you should install libvirt (including headers and Python library) and
NFS.

On Fedora::

    sudo dnf install libvirt-devel libvirt-python nfs-utils

On CentOS/RHEL::

    sudo yum install libvirt-devel libvirt-python nfs-utils

On Ubuntu::

    sudo apt-get install libvirt-dev nfs-commmon nfs-kernel-server python-libvirt qemu* ruby-libvirt

To install vagrant-libvirt plugin::

    vagrant plugin install --plugin-version ">= 0.0.31" vagrant-libvirt

Some Linux distributions offer vagrant-libvirt packages, but the version they
provide tends to be too old to run Kolla-Mesos. A version of >= 0.0.31 is required.

Setup NFS to permit file sharing between host and VMs. Contrary to the rsync
method, NFS allows both way synchronization and offers much better performance
than VirtualBox shared folders. On Fedora 22::

    sudo systemctl start nfs-server
    firewall-cmd --permanent --add-port=2049/udp
    firewall-cmd --permanent --add-port=2049/tcp
    firewall-cmd --permanent --add-port=111/udp
    firewall-cmd --permanent --add-port=111/tcp

Find a location in the system's home directory and checkout the Kolla-Mesos repo::

    git clone https://github.com/openstack/kolla-mesos.git

Developers can now tweak the Vagrantfile or bring up the default AIO
Centos7-based environment::

    cd kolla-mesos/vagrant
    vagrant up

To tweak Vagranfile, you should create *Vagrantfile.custom* file which overrides
some values of *Vagrantfile*. It's recommended to use *Vagrantfile.custom.example*
for that::

    cp Vagrantfile.custom.example Vagrantfile.custom

It's mandatory to set variables in *Vagrantfile.custom* if you want to set up
the multinode environment. In order to do that, this file should contain a line::

    MULTINODE = true

The command ``vagrant status`` provides a quick overview of the VMs composing
the environment.

Vagrant Up
----------

Once Vagrant has completed deploying all nodes, the next step is to
build images using Kolla. First, connect with the *operator* node::

    vagrant ssh operator

To speed things up, there is a local registry running on the operator.  All
nodes are configured so they can use this insecure repo to pull from, and use
it as a mirror. Ansible may use this registry to pull images from.

All nodes have a local folder shared between the group and the hypervisor, and
a folder shared between *all* nodes and the hypervisor.  This mapping is lost
after reboots, so make sure to use the command ``vagrant reload <node>`` when
reboots are required. Having this shared folder provides a method to supply
a different docker binary to the cluster. The shared folder is also used to
store the docker-registry files, so they are save from destructive operations
like ``vagrant destroy``.


Building images
^^^^^^^^^^^^^^^

Log onto the *operator* VM and call the ``kolla-build`` utility. If you're
doing the multinode installation, pushing built images to Docker Registry is
mandatory and you can do this by::

    sudo kolla-build --push --profile mesos

Otherwise, if you're doing the all-in-one installation and don't want to use
the registry::

    sudo kolla-build --profile mesos

``kolla-build`` accepts arguments as documented in :doc:`image-building`. It
builds Docker images and pushes them to the local registry if the *push*
option is enabled (in Vagrant this is the default behaviour).


Setting up Mesos cluster
^^^^^^^^^^^^^^^^^^^^^^^^

To set up a Mesos cluster, the ``kolla-mesos-ansible`` utility should be used.
In case of an all-in-one installation, you can call it without any additional
arguments::

    sudo kolla-mesos-ansible deploy

When you want to provide a custom inventory, you can use the ``--inventory``
option. For example, to use the default multinode inventory (made for
Vagrant)::

    sudo kolla-mesos-ansible -i /usr/share/kolla-mesos/ansible/inventory/multinode deploy

Of course, you can use your custom inventory file for bare metal deployments.


Deploying OpenStack with Kolla-Mesos
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Deploy AIO with::

    kolla-mesos-deploy

Validate OpenStack is operational::

    source ~/openrc
    openstack user list

Or navigate to http://10.10.10.254/ with a web browser.


Further Reading
---------------

All Vagrant documentation can be found at
`docs.vagrantup.com <http://docs.vagrantup.com>`__.
