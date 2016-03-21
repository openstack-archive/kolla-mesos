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
import io

import mock
import six


class FakeConfigFile(object):
    """Contextmanager and decorator for mocking config files.

    :param text_config: contents of configuration to parse by oslo.config
    :type text_config: str
    """
    def __init__(self, text_config):
        self.text_config = text_config

    def __enter__(self):
        if six.PY3:
            func = 'builtins.open'
            return_val = io.StringIO(self.text_config)
        else:
            func = '__builtin__.open'
            return_val = io.BytesIO(self.text_config)

        self.patcher = mock.patch(func, return_value=return_val)
        self.patcher.start()

    def __exit__(self, *args, **kwargs):
        self.patcher.stop()

    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with self:
                return f(*args, **kwargs)
        return wrapper
