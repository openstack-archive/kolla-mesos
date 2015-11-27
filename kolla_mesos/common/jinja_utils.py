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
import os

import jinja2
from jinja2 import meta

LOG = logging.getLogger(__name__)


def jinja_filter_bool(text):
    if not text:
        return False
    if text.lower() in ['true', 'yes']:
        return True
    return False


def jinja_render(fullpath, global_config, extra=None):
    variables = global_config
    if extra:
        variables.update(extra)

    myenv = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            os.path.dirname(fullpath)))
    myenv.filters['bool'] = jinja_filter_bool
    return myenv.get_template(os.path.basename(fullpath)).render(variables)


def jinja_find_required_variables(fullpath):
    myenv = jinja2.Environment(loader=jinja2.FileSystemLoader(
        os.path.dirname(fullpath)))
    myenv.filters['bool'] = jinja_filter_bool
    template_source = myenv.loader.get_source(myenv,
                                              os.path.basename(fullpath))[0]
    parsed_content = myenv.parse(template_source)
    return meta.find_undeclared_variables(parsed_content)
