==================
kolla-mesos-deploy
==================

.. program:: kolla-mesos-deploy

SYNOPSIS
========
``kolla-mesos-deploy [options]``

DESCRIPTION
===========
kolla-mesos-deploy runs kolla containers on Mesos (Marathon+Chronos) cluster.

INVENTORY
=========
kolla-mesos-deploy saves configuration files for each OpenStack service on
ZooKeeper and uses HTTP requests to call Marathon and Chronos API.

OPTIONS
=======

.. cmdoption:: --config-dir DIR

  Path to a config directory to pull .conf files from. This file set is
  sorted, so as to provide a predictable parse order if individual options are
  over-ridden. The set is parsed after the file(s) specified via previous
  --config-file, arguments hence over-ridden options in the directory take
  precedence.

.. cmdoption:: --config-file PATH

  Path to a config file to use. Multiple config files can be specified, with
  values in later files taking precedence. The default files used are: None.

.. cmdoption:: --force

.. cmdoption:: --noforce

  The inverse of --force

.. cmdoption:: --noupdate

  The inverse of --update

.. cmdoption:: --update

.. cmdoption:: --version

  show program's version number and exit

  --profiles-aux PROFILES_AUX
  --profiles-default PROFILES_DEFAULT
  --profiles-gate PROFILES_GATE
  --profiles-infra PROFILES_INFRA
  --profiles-main PROFILES_MAIN

.. cmdoption:: --kolla-base KOLLA_BASE

  The base distro which was used to build images

.. cmdoption:: --kolla-base-tag KOLLA_BASE_TAG

  The base distro image tag

.. cmdoption:: --kolla-install-type KOLLA_INSTALL_TYPE

  The method of the OpenStack install

.. cmdoption:: --kolla-namespace KOLLA_NAMESPACE

  The Docker namespace name

.. cmdoption:: --kolla-profile KOLLA_PROFILE

  Build profile which was used to build images

.. cmdoption:: --kolla-tag KOLLA_TAG

  The Docker tag

.. cmdoption:: --marathon-host MARATHON_HOST

  Marathon connection URL (http://host:port)

.. cmdoption:: --marathon-timeout MARATHON_TIMEOUT

  Timeout for the request to the Marathon API

.. cmdoption:: --zookeeper-host ZOOKEEPER_HOST

  ZooKeeper connection URL (host:port)

.. cmdoption:: --chronos-host CHRONOS_HOST

  Chronos connection URL (http://host:port)

.. cmdoption:: --chronos-timeout CHRONOS_TIMEOUT

  Timeout for the request to the Chronos API

.. cmdoption:: --network-ipv6

  Use IPv6 protocol

.. cmdoption:: --network-noipv6

  The inverse of --ipv6

.. cmdoption:: --network-private-interface NETWORK_PRIVATE_INTERFACE

  NIC connected to the private network

.. cmdoption:: --network-public-interface NETWORK_PUBLIC_INTERFACE

  NIC connected to the public network

FILES
=====

* /etc/kolla-mesos/kolla-mesos.conf
