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

from cliff import command
from oslo_log import log

LOG = log.getLogger(__name__)


class Inspect(command.Command):
    """Show available parameters and info about a service definition."""

    def take_action(self, parsed_args):
        LOG.info('sending greeting')
        LOG.debug('debugging')
        self.app.stdout.write('hi!\n')


class Validate(command.Command):
    """Validate the service definition."""

    def take_action(self, parsed_args):
        LOG.info('sending greeting')
        LOG.debug('debugging')
        self.app.stdout.write('hi!\n')
