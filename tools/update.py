#!/usr/bin/python
# 
# Update selected Mesos/Marathon application.
#
# TODO: group together update-related command line arguments
# TODO: fix positional argument "MARATHON_APP"
# TODO: make an intelligent copy of constraints before updating it 
#       temporairly in same-host scenario
# TODO: implement scenario with multiple tasks within application
#
# sample usage:
# ./update.py --marathon-host http://IP:PORT \
# --marathon-application APP_ID --docker NEW_DOCKER_IMAGE --same-host --debug
#
# (c) mzawadzki@mirantis.com

import argparse
import sys
import json
import time
from kolla_mesos import marathon
from oslo_config import cfg

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('profiles', 'kolla_mesos.config.profiles')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
CONF.import_opt('update', 'kolla_mesos.config.deploy_cli')
CONF.import_opt('force', 'kolla_mesos.config.deploy_cli')

cli_opts = [
  cfg.StrOpt('marathon-application',
             short='a',
             help='name (id) of Mesos/Marathon application to upgrade'
             + '(if not specified existing docker image will be used)'),
  cfg.StrOpt('docker-image',
             short='i',
             help='name of docker image to use for upgrade'),
  cfg.BoolOpt('same-host',
              short='s',
              default=False,
              help='keep upgraded aplication on the same slave'),
  cfg.BoolOpt('debug',
              short='d',
              default=False,
              help='print debugging messages')
]
CONF.register_cli_opts(cli_opts)

# FIXME:
#CONF.register_cli_opt(MultiStrOpt('MARATHON_APP', positional=True))
#^^ should work as: parser.add_argument("MARATHON_APP", help="name 
# of Mesos/Marathon application to upgrade")

CONF(sys.argv[1:])

def debug(str):
  """Prints out debugging message if debugging flag is on.
  :param str: string to print
  :type str: str
  :returns nothing
  """
  if CONF.debug:
    print "[DEBUG] " + str


marathon_client = marathon.Client()

debug("Command line arguments:")
debug("  * id of application to upgrade: " + CONF.marathon_application)
if CONF.docker_image: 
  debug("  * name of docker image        : " + CONF.docker_image)
if CONF.same_host:
  debug("  * keep app on the same slave  : " + str(CONF.same_host))
debug("Marathon version                : " 
      + str(marathon_client.get_version()))
app = marathon_client.get_app(CONF.marathon_application)
debug("Marathon app to upgrade         : " + str(app))

debug("Modyfing app:")
#FIXME: understand why version needs to be removed 
# (otherwise update_app fails):
del app["version"]
if CONF.docker_image: 
  app["container"]["docker"]["image"] = CONF.docker_image
if CONF.same_host: 
  debug("Must keep app on the same host:")
  debug("current host        : " + str(app["tasks"][0]["host"]))
  debug("current constraints : " + str(app["constraints"]))
  debug("setting constraint temporairly:")
  constraints_backup = list(app["constraints"])
  app["constraints"] = [["hostname", "CLUSTER", str(app["tasks"][0]["host"])]]
debug(str(app))
debug("Attepmpting to update the app in Marathon:")
deployment_id = marathon_client.update_app(CONF.marathon_application, app);
debug("deployment id: " + deployment_id)

if CONF.same_host: 
  debug("Restoring original constraints from backup (redeploying).")
  #FIXME: possible race condition here, this should be done after 
  # deployment is complete - host to check it? (or use "force" parameter?)
  app["constraints"] = constraints_backup
  debug("current constraints : " + str(app["constraints"]))
  debug("Attepmpting to update the app in Marathon:")
  time.sleep(5)
  deployment_id = marathon_client.update_app(CONF.marathon_application, app);
  debug("deployment id: " + deployment_id)
