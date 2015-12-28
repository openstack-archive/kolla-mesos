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
import os


# TODO(kproskurin/nihilifer): Make a possibility of decorating classes, not
# only callables.
class FakeEnvironment(object):

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __enter__(self):
        os.environ[self.key] = self.value

    def __exit__(self, *args, **kwargs):
        del os.environ[self.key]

    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with self:
                return f(*args, **kwargs)
        return wrapper
