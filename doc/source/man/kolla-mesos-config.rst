==================
kolla-mesos-config
==================

.. program:: kolla-mesos-config

SYNOPSIS
========

DESCRIPTION
===========

INVENTORY
=========

OPTIONS
=======

.. cmdoption:: --config-dir DIR

  Path to a config directory to pull .conf files from. This file set is sorted,
  so as to provide a predictable parse order if individual options are
  over-ridden. The set is parsed after the file(s) specified via previous
  --config-file, arguments hence over-ridden options in the directory take precedence.

.. cmdoption:: --config-file PATH

  Path to a config file to use. Multiple config files can be specified, with
  values in later files taking precedence. The default files used are: None.

.. cmdoption:: --noshow

  The inverse of --show

.. cmdoption:: --path PATH

.. cmdoption:: --show

.. cmdoption:: --version

  show program's version number and exit

.. cmdoption:: --zookeeper-host ZOOKEEPER_HOST

  ZooKeeper connection URL (host:port)

.. cmdoption:: --network-ipv6

  Use IPv6 protocol

.. cmdoption:: --network-noipv6

  The inverse of --ipv6

.. cmdoption:: --network-private-interface NETWORK_PRIVATE_INTERFACE

  NIC connected to the private network

.. cmdoption:: --network-public-interface NETWORK_PUBLIC_INTERFACE

  NIC connected to the public network
