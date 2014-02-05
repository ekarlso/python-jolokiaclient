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
