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
#

"""
OSM Repo API handling
"""
from osmclient.common.exceptions import ClientException
from osmclient.sol005.repo import Repo
from osmclient.common.package_tool import PackageTool
import requests
import logging
import tempfile
from shutil import copyfile, rmtree
import yaml
import tarfile
import glob
from packaging import version as versioning
import time
from os import listdir, mkdir, getcwd, remove
from os.path import isfile, isdir, join, abspath
import hashlib
from osm_im.validation import Validation as validation_im
import ruamel.yaml


class OSMRepo(Repo):
    def __init__(self, http=None, client=None):
        self._http = http
        self._client = client
        self._apiName = '/admin'
        self._apiVersion = '/v1'
        self._apiResource = '/osmrepos'
        self._logger = logging.getLogger('osmclient')
        self._apiBase = '{}{}{}'.format(self._apiName,
                                        self._apiVersion, self._apiResource)

    def pkg_list(self, pkgtype, filter=None, repo=None):
        """
            Returns a repo based on name or id
        """
        self._logger.debug("")
        self._client.get_token()
        # Get OSM registered repository list
        repositories = self.list()
        if repo:
            repositories = [r for r in repositories if r["name"] == repo]
        if not repositories:
            raise ClientException('Not repository found')

        vnf_repos = []
        for repository in repositories:
            try:
                r = requests.get('{}/index.yaml'.format(repository.get('url')))

                if r.status_code == 200:
                    repo_list = yaml.safe_load(r.text)
                    vnf_packages = repo_list.get('{}_packages'.format(pkgtype))
                    for repo in vnf_packages:
                        versions = vnf_packages.get(repo)
                        latest = versions.get('latest')
                        del versions['latest']
                        for version in versions:
                            latest_version = False
                            if version == latest:
                                latest_version = True
                            vnf_repos.append({'vendor': versions[version].get("vendor"),
                                              'name': versions[version].get("name"),
                                              'version': version,
                                              'description': versions[version].get("description"),
                                              'location': versions[version].get("path"),
                                              'repository': repository.get('name'),
                                              'repourl': repository.get('url'),
                                              'latest': latest_version
                                              })
                else:
                    raise Exception('repository in url {} unreachable'.format(repository.get('url')))
            except Exception as e:
                logging.error("Error cannot read from repository {} '{}': {}".format(repository['name'], repository['url'], e))
                continue

        vnf_repos_filtered = []
        if filter:
            for vnf_repo in vnf_repos:
                for k, v in vnf_repo.items():
                    if v:
                        kf, vf = filter.split('=')
                        if k == kf and vf in v:
                            vnf_repos_filtered.append(vnf_repo)
                            break
            vnf_repos = vnf_repos_filtered
        return vnf_repos

    def get_pkg(self, pkgtype, name, repo, filter, version):
        """
            Returns the filename of the PKG downloaded to disk
        """
        self._logger.debug("")
        self._client.get_token()
        f = None
        f_name = None
        # Get OSM registered repository list
        pkgs = self.pkg_list(pkgtype, filter, repo)
        for pkg in pkgs:
            if pkg.get('repository') == repo and pkg.get('name') == name:
                if 'latest' in version:
                    if not pkg.get('latest'):
                        continue
                    else:
                        version = pkg.get('version')
                if pkg.get('version') == version:
                    r = requests.get('{}{}'.format(pkg.get('repourl'), pkg.get('location')), stream=True)
                    if r.status_code != 200:
                        raise ClientException("Package not found")

                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(r.raw.read())
                        f_name = f.name
                    if not f_name:
                        raise ClientException("{} {} not found at repo {}".format(pkgtype,name, repo))
        return f_name

    def pkg_get(self, pkgtype, name, repo, version, filter):

        pkg_name = self.get_pkg(pkgtype, name, repo, filter, version)
        if not pkg_name:
            raise ClientException('Package not found')
        folder, descriptor = self.zip_extraction(pkg_name)
        with open(descriptor) as pkg:
            pkg_descriptor = yaml.safe_load(pkg)
        rmtree(folder, ignore_errors=False)
        if ((pkgtype == 'vnf' and (pkg_descriptor.get('vnfd') or pkg_descriptor.get('vnfd:vnfd_catalog'))) or
                (pkgtype == 'ns' and (pkg_descriptor.get('nsd') or pkg_descriptor.get('nsd:nsd_catalog')))):
            raise ClientException('Wrong Package type')
        return pkg_descriptor

    def repo_index(self, origin=".", destination='.'):
        """
            Repo Index main function
            :param origin: origin directory for getting all the artifacts
            :param destination: destination folder for create and index the valid artifacts
        """
        if destination == '.':
            if origin == destination:
                destination = 'repository'

        destination = abspath(destination)
        origin = abspath(origin)

        if origin[0] != '/':
            origin = join(getcwd(), origin)
        if destination[0] != '/':
            destination = join(getcwd(), destination)

        self.init_directory(destination)
        artifacts = [f for f in listdir(origin) if isfile(join(origin, f))]
        directories = [f for f in listdir(origin) if isdir(join(origin, f))]
        for artifact in artifacts:
            self.register_artifact_in_repository(join(origin, artifact), destination, source='file')
        for artifact in directories:
            self.register_artifact_in_repository(join(origin, artifact), destination, source='directory')
        print("\nFinal Results: ")
        print("VNF Packages Indexed: " + str(len(glob.glob(destination + "/vnf/*/*/metadata.yaml"))))
        print("NS Packages Indexed: " + str(len(glob.glob(destination + "/ns/*/*/metadata.yaml"))))

    def md5(self, fname):
        """
            Checksum generator
            :param fname: file path
            :return: checksum string
        """
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def fields_building(self, descriptor_json, file, package_type):
        """
            From an artifact descriptor, obtain the fields required for indexing
            :param descriptor_json: artifact description
            :param file: artifact package
            :param package_type: type of artifact (vnf or ns)
            :return: fields
        """
        fields = {}
        base_path = '/{}/'.format(package_type)
        aux_dict = {}
        if package_type == "vnf":
            if descriptor_json.get('vnfd-catalog', False):
                aux_dict = descriptor_json.get('vnfd-catalog', {}).get('vnfd', [{}])[0]
            else:
                aux_dict = descriptor_json.get('vnfd:vnfd-catalog', {}).get('vnfd', [{}])[0]

            images = []
            for vdu in aux_dict.get('vdu', ()):
                images.append(vdu.get('image'))
            fields['images'] = images
        if package_type == "ns":
            if descriptor_json.get('nsd-catalog', False):
                aux_dict = descriptor_json.get('nsd-catalog', {}).get('nsd', [{}])[0]
            else:
                aux_dict = descriptor_json.get('nsd:nsd-catalog', {}).get('nsd', [{}])[0]

            vnfs = []

            for vnf in aux_dict.get('constituent-vnfd', ()):
                vnfs.append(vnf.get('vnfd-id-ref'))
            self._logger.debug('Used VNFS in the NSD: ' + str(vnfs))
            fields['vnfd-id-ref'] = vnfs

        fields['name'] = aux_dict.get('name')
        fields['id'] = aux_dict.get('id')
        fields['description'] = aux_dict.get('description')
        fields['vendor'] = aux_dict.get('vendor')
        fields['version'] = aux_dict.get('version', '1.0')
        fields['path'] = "{}{}/{}/{}-{}.tar.gz".format(base_path, fields['id'], fields['version'], fields.get('id'), \
                          fields.get('version'))
        return fields

    def zip_extraction(self, file_name):
        """
            Validation of artifact.
            :param file: file path
            :return: status details, status, fields, package_type
        """
        self._logger.debug("Decompressing package file")
        temp_file = '/tmp/{}'.format(file_name.split('/')[-1])
        if file_name != temp_file:
            copyfile(file_name, temp_file)
        with tarfile.open(temp_file, "r:gz") as tar:
            folder = tar.getnames()[0].split('/')[0]
            
            import os
            
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(tar)

        remove(temp_file)
        descriptor_file = glob.glob('{}/*.y*ml'.format(folder))[0]
        return folder, descriptor_file

    def validate_artifact(self, path, source):
        """
            Validation of artifact.
            :param path: file path
            :return: status details, status, fields, package_type
        """
        package_type = ''
        folder = ''
        try:
            if source == 'directory':
                descriptor_file = glob.glob('{}/*.y*ml'.format(path))[0]
            else:
                folder, descriptor_file = self.zip_extraction(path)

            self._logger.debug("Opening descriptor file: {}".format(descriptor_file))

            with open(descriptor_file, 'r') as f:
                descriptor_data = f.read()
            validation = validation_im()
            desc_type, descriptor_data = validation.yaml_validation(descriptor_data)
            validation_im.pyangbind_validation(self, desc_type, descriptor_data)
            if 'vnf' in list(descriptor_data.keys())[0]:
                package_type = 'vnf'
            else:
                # raise ClientException("Not VNF package")
                package_type = 'ns'

            self._logger.debug("Descriptor: {}".format(descriptor_data))
            fields = self.fields_building(descriptor_data, path, package_type)
            self._logger.debug("Descriptor sucessfully validated")
            return {"detail": "{}D successfully validated".format(package_type.upper()),
                    "code": "OK"}, True, fields, package_type
        except Exception as e:
            # Delete the folder we just created
            return {"detail": str(e)}, False, {}, package_type
        finally:
            if folder:
                rmtree(folder, ignore_errors=True)

    def register_artifact_in_repository(self, path, destination, source):
        """
            Registration of one artifact in a repository
            file: VNF or NS
            destination: path for index creation
        """
        pt = PackageTool()
        compresed = False
        try:
            fields = {}
            _, valid, fields, package_type = self.validate_artifact(path, source)
            if not valid:
                raise Exception('{} {} Not well configured.'.format(package_type.upper(), str(path)))
            else:
                if source == 'directory':
                    path = pt.build(path)
                    compresed = True
                fields['checksum'] = self.md5(path)
                self.indexation(destination, path, package_type, fields)

        except Exception as e:
            self._logger.debug("Error registering artifact in Repository: {}".format(e))

        finally:
            if source == 'directory' and compresed:
                remove(path)

    def indexation(self, destination, path, package_type, fields):
        """
            Process for index packages
            :param destination: index repository path
            :param path: path of the package
            :param package_type: package type (vnf, ns)
            :param fields: dict with the required values
        """
        data_ind = {'name': fields.get('name'), 'description': fields.get('description'),
                    'vendor': fields.get('vendor'), 'path': fields.get('path')}

        final_path = join(destination, package_type, fields.get('id'), fields.get('version'))
        if isdir(join(destination, package_type, fields.get('id'))):
            if isdir(final_path):
                self._logger.warning('{} {} already exists'.format(package_type.upper(), str(path)))
            else:
                mkdir(final_path)
                copyfile(path,
                         final_path + '/' + fields.get('id') + "-" + fields.get('version') + '.tar.gz')
                yaml.dump(fields, open(final_path + '/' + 'metadata.yaml', 'w'),
                          Dumper=ruamel.yaml.RoundTripDumper)
                index = yaml.load(open(destination + '/index.yaml'))

                index['{}_packages'.format(package_type)][fields.get('id')][fields.get('version')] = data_ind
                if versioning.parse(index['{}_packages'.format(package_type)][fields.get('id')][
                                    'latest']) < versioning.parse(fields.get('version')):
                    index['{}_packages'.format(package_type)][fields.get('id')]['latest'] = fields.get(
                        'version')
                yaml.dump(index, open(destination + '/index.yaml', 'w'), Dumper=ruamel.yaml.RoundTripDumper)
                self._logger.info('{} {} added in the repository'.format(package_type.upper(), str(path)))
        else:
            mkdir(destination + '/{}/'.format(package_type) + fields.get('id'))
            mkdir(final_path)
            copyfile(path,
                     final_path + '/' + fields.get('id') + "-" + fields.get('version') + '.tar.gz')
            yaml.dump(fields, open(join(final_path, 'metadata.yaml'), 'w'), Dumper=ruamel.yaml.RoundTripDumper)
            index = yaml.load(open(destination + '/index.yaml'))

            index['{}_packages'.format(package_type)][fields.get('id')] = {fields.get('version'): data_ind}
            index['{}_packages'.format(package_type)][fields.get('id')]['latest'] = fields.get('version')
            yaml.dump(index, open(join(destination, 'index.yaml'), 'w'), Dumper=ruamel.yaml.RoundTripDumper)
            self._logger.info('{} {} added in the repository'.format(package_type.upper(), str(path)))

    def current_datatime(self):
        """
            Datetime Generator
            :return: Datetime as string with the following structure "2020-04-29T08:41:07.681653Z"
        """
        return time.strftime('%Y-%m-%dT%H:%M:%S.%sZ')

    def init_directory(self, destination):
        """
            Initialize the index directory. Creation of index.yaml, and the directories for vnf and ns
            :param destination:
            :return:
        """
        if not isdir(destination):
            mkdir(destination)
        if not isfile(join(destination, 'index.yaml')):
            mkdir(join(destination, 'vnf'))
            mkdir(join(destination, 'ns'))
            index_data = {'apiVersion': 'v1', 'generated': self.current_datatime(), 'vnf_packages': {},
                          'ns_packages': {}}
            with open(join(destination, 'index.yaml'), 'w') as outfile:
                yaml.dump(index_data, outfile, default_flow_style=False)
