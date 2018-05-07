#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import operator
import os
from functools import reduce
from io import StringIO
from os.path import expanduser
from ruamel.yaml import YAML

from backy2.exception import ConfigurationError, InternalError
from backy2.logging import logger


class Config():

    CONFIG_VERSION = '1.0.0'

    CONFIG_DIR = 'backy2'
    CONFIG_FILE = 'backy2.yaml'

    DEFAULT_CONFIG = """
    logFile: /tmp/backy.log
    blockSize: 4194304
    hashFunction: blake2b,digest_size=32
    lockDirectory: /tmp
    process_name: backy2
    disallowRemoveWhenYounger: 6
    metaBackend:
      type: sql
      sql:
        engine: sqlite:////tmp/backy.sqlite
    dataBackend:
      type: file
      file:
        path: /var/lib/backy2/data
      simultaneousWrites: 1
      simultaneousReads: 1
      bandwidthRead: 0
      bandwidthWrite: 0
      s3_boto3:
        multiDelete: true
        useSsl: true
        addressingStyle: path
        disableEncodingType: false
    nbd:
      cacheDir: /tmp
    io:
      file:
        simultaneousReads: 1
      rbd:
        cephConfigFile: /etc/ceph/ceph.conf
        simultaneousReads: 1
    """

    # Source: https://stackoverflow.com/questions/823196/yaml-merge-in-python
    @classmethod
    def _merge_dicts(cls, user, default):
        if isinstance(user,dict) and isinstance(default,dict):
            for k,v in default.items():
                if k not in user:
                    user[k] = v
                else:
                    user[k] = cls._merge_dicts(user[k],v)
        return user

    def __init__(self, cfg=None, merge_defaults=True):
        yaml = YAML(typ='safe', pure=True)
        default_config = yaml.load(self.DEFAULT_CONFIG)

        if cfg is None:
            sources = self._get_sources()
            for source in sources:
                if os.path.isfile(source):
                    config = yaml.load(source)
                    if config is None:
                        raise ConfigurationError('Configuration file {} is empty.'.format(source))
                    break
            raise ConfigurationError('No configuration file found in the default places ({}).'.format(', '.join(sources)))
        else:
            config = yaml.load(cfg)
            if config is None:
                raise ConfigurationError('Configuration string is empty.')

        if 'configurationVersion' not in config or type(config['configurationVersion']) is not str:
            raise ConfigurationError('Configuration version is missing or not a string.')

        if config['configurationVersion'] != self.CONFIG_VERSION:
            raise ConfigurationError('Unknown configuration version {}.'.format(config['configurationVersion']))

        if merge_defaults:
            self._merge_dicts(config, default_config)

        with StringIO() as loaded_config:
            yaml.dump(config, loaded_config)
            logger.debug('Loaded configuration: {}'.format(loaded_config.getvalue()))

        self.config = config

    def _get_sources(self):
        sources = ['/etc/{file}'.format(file=self.CONFIG_FILE)]
        sources.append('/etc/{dir}/{file}'.format(dir=self.CONFIG_DIR, file=self.CONFIG_FILE))
        sources.append(expanduser('~/.{file}'.format(file=self.CONFIG_FILE)))
        sources.append(expanduser('~/{file}'.format(file=self.CONFIG_FILE)))
        return sources

    @staticmethod
    def _get(dict_, name, *args, types=None):
        if '__position' in dict_:
            full_name = '{}.{}'.format(dict_['__position'], name)
        else:
            full_name = name

        if len(args) > 1:
            raise InternalError('Called with more than two arguments for key {}.'.format(full_name))

        try:
            value = reduce(operator.getitem, name.split('.'), dict_)
            if types is not None and not isinstance(value, types):
                raise TypeError('Config value {} has wrong type {}, expected {}.'.format(full_name, type(value), types))
            if isinstance(value, dict):
                value['__position'] = name
            return value
        except KeyError as e:
            if len(args) == 1:
                return args[0]
            else:
                raise KeyError('Config value {} is missing.'.format(full_name)) from e

    def get(self, name, *args, **kwargs):
        return Config._get(self.config, name, *args, **kwargs)

    @staticmethod
    def get_from_dict(dict_, name, *args, **kwargs):
        return Config._get(dict_, name, *args, **kwargs)

