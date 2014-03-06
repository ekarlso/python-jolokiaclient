# Copyright 2014 Hewlett-Packard Development Company, L.P.
#
# Author: Endre Karlson <endre.karlson@hp.com>
#
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
import logging
import requests

from jolokiaclient import client as jclient


logging.basicConfig(level='DEBUG')

session = requests.Session()
session.auth = ('admin', 'admin',)

http = jclient.HTTPClient('http://localhost:8080/controller/nb/v2/jolokia',
                          debug=True, http=session)
client = jclient.Client(http)

reqs = []

reqs.append(jclient.Request('read', mbean='java.lang:type=Memory'))
reqs.append(jclient.Request('read', mbean='java.lang:type=Threading'))
reqs.append(jclient.Request('read', mbean='java.lang:type=ClassLoading'))

client.do_requests(reqs)
#client.read('java.lang:type=Memory')
