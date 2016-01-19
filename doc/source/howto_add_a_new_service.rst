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

1. kolla-mesos-deploy iterates over all the projects config/<project>
   and finds "services" these are long running process that fulfill
   a useful role (like nova-api within the nova project).
   The main files associated with a service are the following:
   - config/<project>/<service>_config.yml.j2
   - deployment_files/<project>/<service>.marathon.j2

2. parse the _config.yml.j2 file and write the following to zookeeper:
   - the required templates and files
   - the variables that the above templates need.
   - the commands defined in _config.yml.j2

3. parse the marathon and chronos files and deploy them.


The defaults/main.yml file
--------------------------

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


<service>/templates/* files
---------------------------

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


The <service>_config.yml file
-----------------------------

kolla-mesos-deploy uses this file to know what files are placed into
zookeeper from the kolla-mesos repo. Note the config it's self is
copied into zookeeper so that the container can read it too.

kolla_mesos_start.py (within the running container) uses this config to:

1. know where these files are placed within the container.
2. run commands defined in the config

The following is an example of a config with all options used.

.. code-block:: yaml

  config:
    project_a:
      service_x:
        a.cnf.j2:
          source: config/project_a/templates/main.cnf.j2
          dest: /etc/service_x/main.cnf
          owner: service_user
          perm: "0600"
  commands:
    project_a:
      service_x:
        bootstrap:
          command: kolla_extend_start
          env:
            KOLLA_BOOTSTRAP: "yes"
          run_once: True
          register: /kolla/variables/project_a_bootstrap/.done
        doit_please:
          command: /usr/bin/the_service_d
          run_once: False
          daemon: True
          requires: [/kolla/variables/project_a_bootstrap/.done]

Notes on the above config.

1. In the config section, "source" is the source in the kolla-mesos
   source tree and "dest" is the destination in the container. The
   contents of the file will be placed in zookeeper in the node named:
   "/kolla/config/project_a/service_x/a.cnf.j2".
2. kolla_mesos_start.py will render the file before placing in the
   container.
3. In the commands section, commands will be run as soon as their
   "requires" are fulfilled (exist in zookeeper), except that the
   command with "daemon=True" will be kept until last. Once a command
   has completed, kolla_mesos_start.py will create the node "register"
   if it is provided. Command marked with "run_once" will not run
   on more than one node (if the "register" node exists, the command
   will be skipped).


Porting a service from kolla-ansible
------------------------------------

Let's assume that kolla-ansible has the service that you want
supported in kolla-mesos.

initial copying::

  cp ansible/roles/<project>/templates/* ../kolla-mesos/config/<project>/templates/
  cp ansible/roles/<project>/tasks/config.yml ../kolla-mesos/config/<project>/<service>_config.yml
  # then edit the above to the new format.
  cp ansible/roles/<projects>/defaults/main.yml ../kolla-mesos/config/<project>/defaults/main.yml
