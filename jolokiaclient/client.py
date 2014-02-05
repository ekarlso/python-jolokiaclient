# Copyright 2010 Jacob Kaplan-Moss
# Copyright 2011 OpenStack Foundation
# Copyright 2011 Piston Cloud Computing, Inc.
# Copyright 2013 Alessio Ababilov
# Copyright 2013 Grid Dynamics
# Copyright 2013 OpenStack Foundation
# Copyright 2014 HP
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# E0202: An attribute inherited from %s hide this method
# pylint: disable=E0202

import logging
import time

try:
    import simplejson as json
except ImportError:
    import json

import requests

from jolokiaclient import exceptions


LOG = logging.getLogger(__name__)


REQ = {
    'read': [
        {'name': 'mbean', 'required': True},
        {'name': 'attribute'},
        {'name': 'path'}
    ],
    'write': [
        {'name': 'mbean', 'required': True},
        {'name': 'attribute'},
        {'name': 'path'}
    ],
    'list': [
        {'name': 'path'}
    ],
    'version': [],
    'exec': [
        {'name': 'mbean'},
        {'name': 'operation'},
        {'name': 'arguments'}
    ]
}


class HTTPClient(object):
    """This client handles sending HTTP requests to Jolokia servers.

    Features:
    - share authentication information between several clients to different
      services (e.g., for compute and image clients);
    - reissue authentication request for expired tokens;
    - encode/decode JSON bodies;
    - raise exceptions on HTTP errors;
    - pluggable authentication;
    - store authentication information in a keyring;
    - store time spent for requests;
    - register clients for particular services, so one can use
      `http_client.identity` or `http_client.compute`;
    - log requests and responses in a format that is easy to copy-and-paste
      into terminal and send the same request with curl.
    """

    user_agent = "jolokia.apiclient"

    def __init__(self,
                 endpoint,
                 auth_plugin=None,
                 original_ip=None,
                 verify=True,
                 cert=None,
                 timeout=None,
                 timings=False,
                 keyring_saver=None,
                 debug=False,
                 user_agent=None,
                 http=None):
        self.endpoint = endpoint
        self.auth_plugin = auth_plugin

        self.original_ip = original_ip
        self.timeout = timeout
        self.verify = verify
        self.cert = cert

        self.keyring_saver = keyring_saver
        self.debug = debug
        self.user_agent = user_agent or self.user_agent

        self.times = []  # [("item", starttime, endtime), ...]
        self.timings = timings

        # requests within the same session can reuse TCP connections from pool
        self.http = http or requests.Session()

        self.cached_token = None

    def _http_log_req(self, method, url, kwargs):
        if not self.debug:
            return

        string_parts = [
            "curl -i",
            "-X '%s'" % method,
            "'%s'" % url,
        ]

        for element in kwargs['headers']:
            header = "-H '%s: %s'" % (element, kwargs['headers'][element])
            string_parts.append(header)

        LOG.debug("REQ: %s" % " ".join(string_parts))
        if 'data' in kwargs:
            LOG.debug("REQ BODY: %s\n" % (kwargs['data']))

    def _http_log_resp(self, resp):
        if not self.debug:
            return
        LOG.debug(
            "RESP: [%s] %s\n",
            resp.status_code,
            resp.headers)
        if resp._content_consumed:
            LOG.debug(
                "RESP BODY: %s\n",
                resp.text)

    def serialize(self, kwargs):
        if kwargs.get('json') is not None:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['data'] = json.dumps(kwargs['json'])
        try:
            del kwargs['json']
        except KeyError:
            pass

    def get_timings(self):
        return self.times

    def reset_timings(self):
        self.times = []

    def request(self, method, url, **kwargs):
        """Send an http request with the specified characteristics.

        Wrapper around `requests.Session.request` to handle tasks such as
        setting headers, JSON encoding/decoding, and error handling.

        :param method: method of HTTP request
        :param url: URL of HTTP request
        :param kwargs: any other parameter that can be passed to
'            requests.Session.request (such as `headers`) or `json`
             that will be encoded as JSON and used as `data` argument
        """
        kwargs.setdefault("headers", kwargs.get("headers", {}))
        kwargs['headers'].setdefault('Accept', 'application/json')
        kwargs["headers"]["User-Agent"] = self.user_agent
        if self.original_ip:
            kwargs["headers"]["Forwarded"] = "for=%s;by=%s" % (
                self.original_ip, self.user_agent)
        if self.timeout is not None:
            kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify)
        if self.cert is not None:
            kwargs.setdefault("cert", self.cert)
        self.serialize(kwargs)

        self._http_log_req(method, url, kwargs)
        if self.timings:
            start_time = time.time()
        resp = self.http.request(method, url, **kwargs)
        if self.timings:
            self.times.append(("%s %s" % (method, url),
                               start_time, time.time()))
        self._http_log_resp(resp)

        if resp.status_code >= 400:
            LOG.debug(
                "Request returned failure status: %s",
                resp.status_code)
            raise exceptions.from_response(resp, method, url)

        return resp

    @staticmethod
    def concat_url(endpoint, url):
        """Concatenate endpoint and final URL.

        E.g., "http://keystone/v2.0/" and "/tokens" are concatenated to
        "http://keystone/v2.0/tokens".

        :param endpoint: the base URL
        :param url: the final URL
        """
        u = "%s/%s" % (endpoint.rstrip("/"), url.strip("/"))
        return u.rstrip('/')

    def client_request(self, client, method, url, **kwargs):
        try:
            return self.request(
                method, self.concat_url(self.endpoint, url), **kwargs)
        except Exception as e:
            if hasattr(e, 'details'):
                LOG.error("Error from server below:\n%s", e.details)
            raise

    def add_client(self, base_client_instance):
        """Add a new instance of :class:`BaseClient` descendant.

        `self` will store a reference to `base_client_instance`.

        Example:

        >>> def test_clients():
        ...     from keystoneclient.auth import keystone
        ...     from openstack.common.apiclient import client
        ...     auth = keystone.KeystoneAuthPlugin(
        ...         username="user", password="pass", tenant_name="tenant",
        ...         auth_url="http://auth:5000/v2.0")
        ...     openstack_client = client.HTTPClient(auth)
        ...     # create nova client
        ...     from novaclient.v1_1 import client
        ...     client.Client(openstack_client)
        ...     # create keystone client
        ...     from keystoneclient.v2_0 import client
        ...     client.Client(openstack_client)
        ...     # use them
        ...     openstack_client.identity.tenants.list()
        ...     openstack_client.compute.servers.list()
        """
        service_type = base_client_instance.service_type
        if service_type and not hasattr(self, service_type):
            setattr(self, service_type, base_client_instance)

    def authenticate(self):
        self.auth_plugin.authenticate(self)


class BaseClient(object):
    service_type = None

    def __init__(self, http_client, extensions=None):
        self.http_client = http_client
        http_client.add_client(self)

        # Add in any extensions...
        if extensions:
            for extension in extensions:
                if extension.manager_class:
                    setattr(self, extension.name,
                            extension.manager_class(self))

    def client_request(self, method, url, **kwargs):
        return self.http_client.client_request(
            self, method, url, **kwargs)

    def _head(self, url, **kwargs):
        return self.client_request("HEAD", url, **kwargs)

    def _get(self, url, **kwargs):
        return self.client_request("GET", url, **kwargs)

    def _post(self, url, **kwargs):
        return self.client_request("POST", url, **kwargs)

    def _put(self, url, **kwargs):
        return self.client_request("PUT", url, **kwargs)

    def _delete(self, url, **kwargs):
        return self.client_request("DELETE", url, **kwargs)

    def _patch(self, url, **kwargs):
        return self.client_request("PATCH", url, **kwargs)


class Request(object):
    def __init__(self, type, **kwargs):
        self.type = type
        self.kwargs = kwargs

    def as_dict(self):
        data = {'type': self.type}
        for o in REQ[self.type]:
            if o['name'] in self.kwargs:
                value = self.kwargs[o['name']]
                data[o['name']] = value
            else:
                if o.get('required'):
                    raise exceptions.MissingArgs
        return data


class Client(BaseClient):
    def __init__(self, *args, **kw):
        self.jolokia_base = kw.pop('jolokia_base', '/jolokia')
        super(Client, self).__init__(*args, **kw)

    def read(self, mbean, attribute=None, path=None):
        r = Request('read', mbean=mbean, attribute=attribute, path=path)
        return self.do_requests([r])[0]

    def do_requests(self, requests):
        data = [r.as_dict() for r in requests]
        resp = self._post(self.jolokia_base, json=data)
        return resp.json()


def make_requests(data):
    return [Request(**req) for req in data]
