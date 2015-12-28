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

import prettytable
import six


def lister(column_names, data):
    table = prettytable.PrettyTable(column_names, print_empty=False)
    for data_row in data:
        table.add_row(data_row)
    print(table.get_string())


def show(column_names, data):
    table = prettytable.PrettyTable(('Field', 'Value',), print_empty=False)
    for column_name, data_row in six.moves.zip(column_names, data):
        table.add_row((column_name, data_row,))
    print(table.get_string())
