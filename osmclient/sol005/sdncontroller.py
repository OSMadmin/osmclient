# Copyright 2018 Telefonica
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

"""
OSM SDN controller API handling
"""

from osmclient.common import utils
from osmclient.common.exceptions import ClientException
from osmclient.common.exceptions import NotFound
import yaml 


class SdnController(object):
    def __init__(self, http=None, client=None):
        self._http = http
        self._client = client
        self._apiName = '/admin'
        self._apiVersion = '/v1'
        self._apiResource = '/sdns'
        self._apiBase = '{}{}{}'.format(self._apiName,
                                        self._apiVersion, self._apiResource)
    def create(self, name, sdn_controller):
        resp = self._http.post_cmd(endpoint=self._apiBase,
                                       postfields_dict=sdn_controller)
        #print 'RESP: {}'.format(resp)
        if not resp or 'id' not in resp:
            raise ClientException('failed to create SDN controller: '.format(
                                  resp))
        else:
            print resp['id']

    def update(self, name, sdn_controller):
        sdnc = self.get(name)
        resp = self._http.patch_cmd(endpoint='{}/{}'.format(self._apiBase,sdnc['_id']),
                                       postfields_dict=sdn_controller)
        print 'RESP: {}'.format(resp)
        if not resp or 'id' not in resp:
            raise ClientException('failed to update SDN controller: '.format(
                                  resp))
        else:
            print resp['id']

    def delete(self, name):
        sdn_controller = self.get(name)
        http_code, resp = self._http.delete_cmd('{}/{}'.format(self._apiBase,sdn_controller['_id']))
        #print 'RESP: {}'.format(resp)
        if http_code == 202:
            print 'Deletion in progress'
        elif http_code == 204:
            print 'Deleted'
        elif 'result' in resp:
            print 'Deleted'
        else:
            raise ClientException("failed to delete vim {} - {}".format(name, resp))

    def list(self, filter=None):
        """Returns a list of SDN controllers
        """
        filter_string = ''
        if filter:
            filter_string = '?{}'.format(filter)
        resp = self._http.get_cmd('{}{}'.format(self._apiBase,filter_string))
        #print 'RESP: {}'.format(resp)
        if resp:
            return resp
        return list()

    def get(self, name):
        """Returns an SDN controller based on name or id
        """
        if utils.validate_uuid4(name):
            for sdnc in self.list():
                if name == sdnc['_id']:
                    return sdnc
        else:
            for sdnc in self.list():
                if name == sdnc['name']:
                    return sdnc
        raise NotFound("SDN controller {} not found".format(name))


