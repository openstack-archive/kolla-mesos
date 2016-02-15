..
      Copyright 2014-2015 OpenStack Foundation
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.



How to add a new service
========================

Overview
--------
Firstly let's go through how a deployment works when you run
kolla-mesos-deploy to better understand the flow of operation.

1. kolla-mesos-deploy iterates over all the projects specified in
   the chosen profile. It then finds services and task definitions
   in services/<project>/*.yml.j2.

2. parse the service definition file and write the following to zookeeper:
   - the required templates and files
   - the variables that the above templates need.
   - the definition it's self

3. generate the marathon and chronos files and deploy them.


The config/<project>/defaults/main.yml
--------------------------------------

This file keeps the basic variables which will be used when generating the
other files. Of course it can re-use wariables from *config/all.yml* file
which stores global variables for the whole kolla-mesos project.

We usually store the following information in this kind of files:

* database name, user and address
* Docker image name and tag
* OpenStack credentials and options

An example:

.. code-block:: yaml

  project_name: "keystone"

  keystone_database_name: "keystone"
  keystone_database_user: "keystone"
  keystone_database_address: "{{ kolla_internal_address }}

  keystone_image: "{{ docker_registry ~ '/' if docker_registry else '' }}{{ docker_namespace }}/{{ kolla_base_distro }}-{{ kolla_install_type }}-keystone"
  keystone_tag: "{{ openstack_release }}"

  keystone_public_address: "{{ kolla_external_address }}"
  keystone_admin_address: "{{ kolla_internal_address }}"
  keystone_internal_address: "{{ kolla_internal_address }}"

  keystone_logging_verbose: "{{ openstack_logging_verbose }}"
  keystone_logging_debug: "{{ openstack_logging_debug }}"


config/<project>/templates/*
----------------------------

kolla-mesos uses these files to generate the configuration of OpenStack
services. You can use jinja2 variables here. Generally, such a config file
should follow the practices used for creating usual config files.

An example::

  [DEFAULT]
  verbose = {{ keystone_logging_verbose }}
  debug = {{ keystone_logging_debug}}

  admin_token = {{ keystone_admin_token }}

  [database]
  connection = mysql://{{ keystone_database_user }}:{{ keystone_database_password }}@{{ keystone_database_address }}/{{ keystone_database_name }}


The service definition file
---------------------------

kolla-mesos-deploy uses this file to know what files are placed into
zookeeper from the kolla-mesos repo. Note the config it's self is
copied into zookeeper so that the container can read it too.

kolla_mesos_start.py (within the running container) uses this config to:

1. know where these files are placed within the container.
2. run commands defined in the config

The following is an example of a service.

.. code-block:: yaml

  name: openstack/cinder/cinder-api
  enabled: {{ enable_cinder | bool }}
  container:
    # place any marathon/container attribute here
    # note the container/docker attributes do not need extra nesting
    # they will be placed correctly in container/docker/
    privileged: false
    image: "{{ cinder_api_image }}:{{ cinder_api_tag }}"
  service:
    # place any toplevel marathon attribute here
    # see: https://mesosphere.github.io/marathon/docs/rest-api.html
    constraints: [["attribute", "OPERATOR", "value"]]
    cpus: 1.5
    mem: 256.0
    instances: 3
    daemon:
      dependencies: [rabbitmq/daemon, cinder-api/db_sync]
      command: /usr/bin/cinder-api
  commands:
    db_sync:
      env:
        KOLLA_BOOTSTRAP:
      command: kolla_extend_start
      run_once: True
      dependencies: [cinder_ansible_tasks/create_database,
                     cinder_ansible_tasks/database_user_create]
      files:
        cinder.conf.j2:
          source: /etc/kolla-mesos/config/cinder/cinder-api.conf
          dest: /etc/cinder/cinder.conf
          owner: cinder
          perm: "0600"


The following is an example of a task.

.. code-block:: yaml

  name: openstack/cinder/task
  enabled: {{ enable_cinder | bool }}
  container:
    # place any chronos/container attribute here
    volumes:
      -
        containerPath: "/var/log/"
        hostPath: "/logs/"
        mode: "RW"
    image: "{{ kolla_toolbox_image }}:{{ kolla_toolbox_tag }}"
  task:
    # place any toplevel chronos attribute here
    # see: https://mesos.github.io/chronos/docs/api.html
    cpus: 1.5
    mem: 256.0
    retries: 2
  commands:
    db_sync:
      env:
        KOLLA_BOOTSTRAP:
      command: kolla_extend_start
      run_once: True
      dependencies: [cinder_ansible_tasks/create_database,
                     cinder_ansible_tasks/database_user_create]
      files:
        cinder.conf.j2:
          source: /etc/kolla-mesos/config/cinder/cinder-api.conf
          dest: /etc/cinder/cinder.conf
          owner: cinder
          perm: "0600"



Notes on the above config.

1. In the files section, "source" is the source in the kolla-mesos
   source tree and "dest" is the destination in the container. The
   contents of the file will be placed in zookeeper in the node named:
   "/kolla/config/project_a/service_x/a.cnf.j2".
2. kolla_mesos_start.py will render the file before placing in the
   container.
3. In the commands section, commands will be run as soon as their
   "dependencies" are fulfilled (exist in zookeeper), except that the
   daemon command will be kept until last. Once a command
   has completed, kolla_mesos_start.py will create the node in zookeeper.
   Commands marked with "run_once" will not run
   on more than one node.


Porting a service from kolla-ansible
------------------------------------

Let's assume that kolla-ansible has the service that you want
supported in kolla-mesos.

initial copying::

  cp ansible/roles/<project>/templates/* ../kolla-mesos/config/<project>/templates/
  cp ansible/roles/<project>/tasks/config.yml ../kolla-mesos/config/<project>/<service>_config.yml
  # then edit the above to the new format.
  cp ansible/roles/<projects>/defaults/main.yml ../kolla-mesos/config/<project>/defaults/main.yml
