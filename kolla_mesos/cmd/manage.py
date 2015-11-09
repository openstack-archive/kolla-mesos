#!/usr/bin/env python

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

import argparse
import ConfigParser
# import json
import logging
import signal

# import requests

from kolla_mesos import utils
from kolla_mesos import worker


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

signal.signal(signal.SIGINT, signal.SIG_DFL)


def merge_args_and_config(settings_from_config_file):
    parser = argparse.ArgumentParser(description='Kolla build script')

    defaults = {
        "namespace": "kollaglue",
        "tag": "latest",
        "base": "centos",
        "base_tag": "latest",
        "install_type": "binary",
        "kolla_dir": "/home/angus/work/kolla",
    }
    defaults.update(settings_from_config_file)
    parser.set_defaults(**defaults)

    parser.add_argument('-n', '--namespace',
                        help='Set the Docker namespace name',
                        type=str)
    parser.add_argument('--tag',
                        help='Set the Docker tag',
                        type=str)
    parser.add_argument('-b', '--base',
                        help='The base distro to use when building',
                        type=str)
    parser.add_argument('--base-tag',
                        help='The base distro image tag',
                        type=str)
    parser.add_argument('-t', '--type',
                        help='The method of the Openstack install',
                        type=str,
                        dest='install_type')
    parser.add_argument('--template',
                        help='DEPRECATED: All appfiles are templates',
                        action='store_true',
                        default=True)
    parser.add_argument('-d', '--debug',
                        help='Turn on debugging log level',
                        action='store_true')
    parser.add_argument('--template-only',
                        help=("Don't build images. Generate Dockerfile only"),
                        action='store_true')
    parser.add_argument('-p', '--profile',
                        help=('Build a pre-defined set of images, see '
                              '[profiles] section in '
                              '{}'.format(
                                  utils.find_config_file('kolla-build.conf'))),
                        type=str,
                        action='append')

    return vars(parser.parse_args())


def main():
    # need kolla-build, profiles, globals

    kolla_config = ConfigParser.SafeConfigParser()
    kolla_config.read(utils.find_config_file('kolla-build.conf'))
    build_config = merge_args_and_config(kolla_config.items('kolla-build'))
    if build_config['debug']:
        LOG.setLevel(logging.DEBUG)
    profiles = dict(kolla_config.items('profiles'))

    kolla = worker.KollaWorker(build_config, profiles)
    kolla.setup_working_dir()

    # run jinja over the marathon app (pass in the above kolla config)
    kolla.parse_app_files()

    if build_config['template_only']:
        LOG.info('files are generated in {}'.format(kolla.temp_dir))
        return

    # kolla.write_config_to_zookeeper()

    # start the apps
    # kolla.start()
    # curl -X POST http://$HOST_IP:8080/v2/apps -d @marathon/mariadb.json \
    # -H "Content-type: application/json"


if __name__ == '__main__':
    main()
