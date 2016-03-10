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

import functools
import sys

import six

from kolla_mesos.common import type_utils


def yes_no_prompt(msg):
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            full_msg = '%s [y/n] ' % msg
            yes_no = six.moves.input(full_msg)
            yes_no = type_utils.str_to_bool(yes_no)
            if not yes_no:
                sys.exit(1)
            return f(*args, **kwargs)
        return wrapped
    return wrapper
