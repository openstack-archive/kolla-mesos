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

import retrying

from kolla_mesos import exception as kolla_mesos_exc


def check_if_not_rollback(exception):
    return not isinstance(exception, kolla_mesos_exc.MarathonRollback)


def retry_if_not_rollback(*retry_args, **retry_kwargs):
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            retry_kwargs['retry_on_exception'] = check_if_not_rollback
            decorated_function = retrying.retry(*retry_args, **retry_kwargs)(f)
            return decorated_function(*args, **kwargs)
        return wrapped
    return wrapper
