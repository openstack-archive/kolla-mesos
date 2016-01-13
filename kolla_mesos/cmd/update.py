#!/usr/bin/python
#
# Update selected Mesos/Marathon application.
#
# TODO(mzawadzki): group together update-related command line arguments
# TODO(mzawadzki): make an intelligent copy of constraints before updating it
#                  temporairly in same-host scenario
# TODO(mzawadzki): implement scenario with multiple tasks within application
#
# sample usage:
# ./update.py --marathon-host http://IP:PORT --docker NEW_DOCKER_IMAGE \
# --same-host --debug APP_ID
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from kolla_mesos import marathon
import logging
from oslo_config import cfg
import sys
import time

CONF = cfg.CONF
CONF.import_group('marathon', 'kolla_mesos.config.marathon')

cli_opts = [
    cfg.StrOpt('application',
               help='name (id) of Mesos/Marathon application to update',
               positional=True),
    cfg.StrOpt('docker-image',
               short='i',
               help='name of docker image to use for update'),
    cfg.BoolOpt('same-host',
                short='s',
                default=False,
                help='keep updated aplication on the same slave'),
    cfg.BoolOpt('debug',
                short='d',
                default=False,
                help='print debugging messages'),
]
CONF.register_cli_opts(cli_opts)

CONF(sys.argv[1:])

logging.basicConfig()
LOG = logging.getLogger(__name__)
if CONF.debug:
    LOG.setLevel(logging.DEBUG)
else:
    LOG.setLevel(logging.INFO)


def main():
    marathon_client = marathon.Client()

    LOG.debug("Command line arguments:")
    LOG.debug("  * id of application to update: " + CONF.application)
    if CONF.docker_image:
        LOG.debug("  * name of docker image        : " + CONF.docker_image)
    if CONF.same_host:
        LOG.debug("  * keep app on the same slave  : " + str(CONF.same_host))
    LOG.debug("Marathon version                : "
              + str(marathon_client.get_version()))
    app = marathon_client.get_app(CONF.application)
    LOG.debug("Marathon app to update  : " + str(app))

    LOG.debug("Modyfing app:")
    # FIXME(mzawadzki): understand why version needs to be removed
    # (otherwise update_app fails):
    del app["version"]
    if CONF.docker_image:
        app["container"]["docker"]["image"] = CONF.docker_image
    if CONF.same_host:
        LOG.debug("Must keep app on the same host:")
        LOG.debug("current host        : " + str(app["tasks"][0]["host"]))
        LOG.debug("current constraints : " + str(app["constraints"]))
        LOG.debug("setting constraint temporairly:")
        constraints_backup = list(app["constraints"])
        app["constraints"] = [
            ["hostname", "CLUSTER", str(app["tasks"][0]["host"])]
            ]
    LOG.debug(str(app))
    LOG.debug("Attepmpting to update the app in Marathon:")
    deployment_id = marathon_client.update_app(CONF.application, app)
    LOG.debug("deployment id: " + deployment_id)

    if CONF.same_host:
        LOG.debug("Restoring original constraints from backup (redeploying).")
        # FIXME(mzawadzki): possible race condition here, this should be done
        # after deployment is complete - host to check it? (or use "force"
        # parameter?)
        app["constraints"] = constraints_backup
        LOG.debug("current constraints : " + str(app["constraints"]))
        LOG.debug("Attepmpting to update the app in Marathon:")
        time.sleep(5)
        deployment_id = marathon_client.update_app(CONF.application,
                                                   app)
        LOG.debug("deployment id: " + deployment_id)


if __name__ == '__main__':
    main()
