# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import contextlib
import os.path
import sys

from oslo_config import cfg
from oslotest import base
import six
import testscenarios


# Python 3, thank you for dropping contextlib.nested
if six.PY3:
    @contextlib.contextmanager
    def nested(*contexts):
        with contextlib.ExitStack() as stack:
            yield [stack.enter_context(c) for c in contexts]
else:
    nested = contextlib.nested


class BaseTestCase(testscenarios.WithScenarios,
                   base.BaseTestCase):
    """Test case base class for all unit tests."""

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.addCleanup(cfg.CONF.reset)
        mod_dir = os.path.dirname(sys.modules[__name__].__file__)
        self.project_dir = os.path.abspath(os.path.join(mod_dir, '..', '..'))
