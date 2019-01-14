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
OSM wim API handling
"""

from osmclient.common import utils
from osmclient.common.exceptions import ClientException
from osmclient.common.exceptions import NotFound
import yaml
import json


class Wim(object):
    def __init__(self, http=None, client=None):
        self._http = http
        self._client = client
        self._apiName = '/admin'
        self._apiVersion = '/v1'
        self._apiResource = '/wim_accounts'
        self._apiBase = '{}{}{}'.format(self._apiName,
                                        self._apiVersion, self._apiResource)
    def create(self, name, wim_input, wim_port_mapping=None):
        if 'wim_type' not in wim_input:
            raise Exception("wim type not provided")

        wim_account = wim_input
        wim_account["name"] = name

        wim_config = {}
        if 'config' in wim_input and wim_input['config'] is not None:
            wim_config = yaml.safe_load(wim_input['config'])
        if wim_port_mapping:
            with open(wim_port_mapping, 'r') as f:
                wim_config['wim_port_mapping'] = yaml.safe_load(f.read())
        if wim_config:
            wim_account['config'] = wim_config
            #wim_account['config'] = json.dumps(wim_config)

        http_code, resp = self._http.post_cmd(endpoint=self._apiBase,
                                       postfields_dict=wim_account)
        #print 'HTTP CODE: {}'.format(http_code)
        #print 'RESP: {}'.format(resp)
        if http_code in (200, 201, 202, 204):
            if resp:
                resp = json.loads(resp)
            if not resp or 'id' not in resp:
                raise ClientException('unexpected response from server - {}'.format(
                                      resp))
            print(resp['id'])
        else:
            msg = ""
            if resp:
                try:
                    msg = json.loads(resp)
                except ValueError:
                    msg = resp
            raise ClientException("failed to create wim {} - {}".format(name, msg))

    def update(self, wim_name, wim_account, wim_port_mapping=None):
        wim = self.get(wim_name)

        wim_config = {}
        if 'config' in wim_account:
            if wim_account.get('config')=="" and (wim_port_mapping):
                raise ClientException("clearing config is incompatible with updating SDN info")
            if wim_account.get('config')=="":
                wim_config = None
            else:
                wim_config = yaml.safe_load(wim_account['config'])
        if wim_port_mapping:
            with open(wim_port_mapping, 'r') as f:
                wim_config['wim_port_mapping'] = yaml.safe_load(f.read())
        wim_account['config'] = wim_config
        #wim_account['config'] = json.dumps(wim_config)
        http_code, resp = self._http.put_cmd(endpoint='{}/{}'.format(self._apiBase,wim['_id']),
                                       postfields_dict=wim_account)
        #print 'HTTP CODE: {}'.format(http_code)
        #print 'RESP: {}'.format(resp)
        if http_code in (200, 201, 202, 204):
            pass
        else:
            msg = ""
            if resp:
                try:
                    msg = json.loads(resp)
                except ValueError:
                    msg = resp
            raise ClientException("failed to update wim {} - {}".format(wim_name, msg))

    def update_wim_account_dict(self, wim_account, wim_input):
        print (wim_input)
        wim_account['wim_type'] = wim_input['wim_type']
        wim_account['description'] = wim_input['description']
        wim_account['wim_url'] = wim_input['url']
        wim_account['user'] = wim_input.get('wim-username')
        wim_account['password'] = wim_input.get('wim-password')
        return wim_account

    def get_id(self, name):
        """Returns a VIM id from a VIM name
        """
        for wim in self.list():
            if name == wim['name']:
                return wim['uuid']
        raise NotFound("wim {} not found".format(name))

    def delete(self, wim_name, force=False):
        wim_id = wim_name
        if not utils.validate_uuid4(wim_name):
            wim_id = self.get_id(wim_name)
        querystring = ''
        if force:
            querystring = '?FORCE=True'
        http_code, resp = self._http.delete_cmd('{}/{}{}'.format(self._apiBase,
                                         wim_id, querystring))
        #print 'HTTP CODE: {}'.format(http_code)
        #print 'RESP: {}'.format(resp)
        if http_code == 202:
            print('Deletion in progress')
        elif http_code == 204:
            print('Deleted')
        else:
            msg = ""
            if resp:
                try:
                    msg = json.loads(resp)
                except ValueError:
                    msg = resp
            raise ClientException("failed to delete wim {} - {}".format(wim_name, msg))

    def list(self, filter=None):
        """Returns a list of VIM accounts
        """
        filter_string = ''
        if filter:
            filter_string = '?{}'.format(filter)
        resp = self._http.get_cmd('{}{}'.format(self._apiBase,filter_string))
        if not resp:
            return list()
        wim_accounts = []
        for datacenter in resp:
            wim_accounts.append({"name": datacenter['name'], "uuid": datacenter['_id']
                        if '_id' in datacenter else None})
        return wim_accounts

    def get(self, name):
        """Returns a VIM account based on name or id
        """
        wim_id = name
        if not utils.validate_uuid4(name):
            wim_id = self.get_id(name)
        resp = self._http.get_cmd('{}/{}'.format(self._apiBase,wim_id))
        if not resp or '_id' not in resp:
            raise ClientException('failed to get wim info: '.format(
                                  resp))
        else:
            return resp
        raise NotFound("wim {} not found".format(name))

