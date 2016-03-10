######################################################################
#
# File: test_bucket.py
#
# Copyright 2015 Backblaze Inc. All Rights Reserved.
#
# License https://www.backblaze.com/using_b2_code.html
#
######################################################################

from __future__ import absolute_import, print_function

from b2.b2 import AbstractAccountInfo, B2Api
from b2.raw_simulator import RawSimulator
import six
import unittest


class StubAccountInfo(AbstractAccountInfo):
    def __init__(self):
        self.clear()

    def clear(self):
        self.account_id = None
        self.auth_token = None
        self.api_url = None
        self.download_url = None
        self.buckets = {}

    def set_account_id_and_auth_token(self, account_id, auth_token, api_url, download_url):
        self.account_id = account_id
        self.auth_token = auth_token
        self.api_url = api_url
        self.download_url = download_url

    def set_bucket_upload_data(self, bucket_id, upload_url, upload_auth_token):
        self.buckets[bucket_id] = (upload_url, upload_auth_token)

    def get_account_id(self):
        return self.account_id

    def get_account_auth_token(self):
        return self.auth_token

    def get_api_url(self):
        return self.api_url

    def get_download_url(self):
        return self.download_url

    def get_bucket_upload_data(self, bucket_id):
        return self.buckets.get(bucket_id, (None, None))


class TestLs(unittest.TestCase):
    def setUp(self):
        self.bucket_name = 'my-bucket'
        self.simulator = RawSimulator()
        self.account_info = StubAccountInfo()
        self.api = B2Api(self.account_info, raw_api=RawSimulator())
        self.api.authorize_account('http://realm.example.com', 'my-account', 'my-key')
        self.bucket = self.api.create_bucket('my-bucket', 'allPublic')

    def test_empty(self):
        self.assertEqual([], list(self.bucket.ls('foo')))

    def test_one_file_at_root(self):
        data = six.b('hello world')
        self.bucket.upload_bytes(data, 'hello.txt')
        expected = [('hello.txt', 11, 'upload', None)]
        actual = [
            (info.file_name, info.size, info.action, folder)
            for (info, folder) in self.bucket.ls('')
        ]
        self.assertEqual(expected, actual)

    def test_three_files_at_root(self):
        data = six.b('hello world')
        self.bucket.upload_bytes(data, 'a')
        self.bucket.upload_bytes(data, 'bb')
        self.bucket.upload_bytes(data, 'ccc')
        expected = [
            ('a', 11, 'upload', None), ('bb', 11, 'upload', None), ('ccc', 11, 'upload', None)
        ]
        actual = [
            (info.file_name, info.size, info.action, folder)
            for (info, folder) in self.bucket.ls('')
        ]
        self.assertEqual(expected, actual)

    def test_three_files_in_dir(self):
        data = six.b('hello world')
        self.bucket.upload_bytes(data, 'a')
        self.bucket.upload_bytes(data, 'bb/1')
        self.bucket.upload_bytes(data, 'bb/2/sub1')
        self.bucket.upload_bytes(data, 'bb/2/sub2')
        self.bucket.upload_bytes(data, 'bb/3')
        self.bucket.upload_bytes(data, 'ccc')
        expected = [
            ('bb/1', 11, 'upload', None), ('bb/2/sub1', 11, 'upload', 'bb/2/'),
            ('bb/3', 11, 'upload', None)
        ]
        actual = [
            (info.file_name, info.size, info.action, folder)
            for (info, folder) in self.bucket.ls(
                'bb',
                fetch_count=1
            )
        ]
        self.assertEqual(expected, actual)

    def test_three_files_multiple_versions(self):
        data = six.b('hello world')
        self.bucket.upload_bytes(data, 'a')
        self.bucket.upload_bytes(data, 'bb/1')
        self.bucket.upload_bytes(data, 'bb/2')
        self.bucket.upload_bytes(data, 'bb/2')
        self.bucket.upload_bytes(data, 'bb/2')
        self.bucket.upload_bytes(data, 'bb/3')
        self.bucket.upload_bytes(data, 'ccc')
        expected = [
            ('9998', 'bb/1', 11, 'upload', None), ('9995', 'bb/2', 11, 'upload', None),
            ('9996', 'bb/2', 11, 'upload', None), ('9997', 'bb/2', 11, 'upload', None),
            ('9994', 'bb/3', 11, 'upload', None)
        ]
        actual = [
            (info.id_, info.file_name, info.size, info.action, folder)
            for (info, folder) in self.bucket.ls(
                'bb',
                show_versions=True,
                fetch_count=1
            )
        ]
        self.assertEqual(expected, actual)