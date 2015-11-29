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

import logging

from six.moves import configparser

from kolla_mesos.common import file_utils

LOG = logging.getLogger(__name__)


def load(config_name, merge_args_and_config):
    kolla_config = configparser.SafeConfigParser()
    kolla_config.read(file_utils.find_config_file(config_name))
    cmd_opts = merge_args_and_config(kolla_config)
    if cmd_opts['debug']:
        LOG.setLevel(logging.DEBUG)
    return cmd_opts, kolla_config
