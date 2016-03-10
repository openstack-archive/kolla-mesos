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

import sys

from oslo_config import cfg
from oslo_log import log as logging

from kolla_mesos import cleanup
from kolla_mesos.common import warning_utils


CONF = cfg.CONF
CONF.import_opt('workers', 'kolla_mesos.config.multiprocessing_cli')

LOG = logging.getLogger()
logging.register_options(CONF)


@warning_utils.yes_no_prompt("This is a tool made mostly for the development "
                             "purposes. It removes all the kolla containers "
                             "in the whole cluster using SSH connection. It's "
                             "not recommended to use it on production. Do you "
                             "want to continue?")
def main():
    CONF(sys.argv[1:], project='kolla-mesos')
    logging.setup(CONF, 'kolla-mesos')
    cleanup.cleanup()


if __name__ == '__main__':
    main()
