import logging
import requests

from jolokiaclient import client as jclient


logging.basicConfig(level='DEBUG')

session = requests.Session()
session.auth = ('admin', 'admin',)

http = jclient.HTTPClient('http://localhost:8080/controller/nb/v2/jolokia',
                          debug=True, http=session)
client = jclient.Client(http)

client.read('java.lang:type=Memory')
