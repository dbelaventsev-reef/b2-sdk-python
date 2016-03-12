######################################################################
#
# File: raw_simulator.py
#
# Copyright 2015 Backblaze Inc. All Rights Reserved.
#
# License https://www.backblaze.com/using_b2_code.html
#
######################################################################

from .b2 import BadUploadUrl, DuplicateBucketName, FileNotPresent, NonExistentBucket, RawApi
import re
import six
from six.moves import range
import time


class PartSimulator(object):
    pass


class FileSimulator(object):
    """
    One of: an unfinished large file, a finished file, or a deletion marker
    """

    def __init__(
        self, account_id, bucket_id, file_id, action, name, content_type, content_sha1, file_info,
        data_bytes
    ):
        self.account_id = account_id
        self.bucket_id = bucket_id
        self.file_id = file_id
        self.action = action
        self.name = name
        if data_bytes is not None:
            self.content_length = len(data_bytes)
        self.content_type = content_type
        self.content_sha1 = content_sha1
        self.file_info = file_info
        self.data_bytes = data_bytes
        self.upload_timestamp = int(time.time() * 1000)

        if action == 'start':
            self.parts = []

    def sort_key(self):
        """
        Returns a key that can be used to sort the files in a
        bucket in the order that b2_list_file_versions returns them.
        """
        return (self.name, self.file_id)

    def as_upload_result(self):
        return dict(
            fileId=self.file_id,
            fileName=self.name,
            accountId=self.account_id,
            bucketId=self.bucket_id,
            contentLength=len(self.data_bytes),
            contentType=self.content_type,
            contentSha1=self.content_sha1,
            fileInfo=self.file_info
        )

    def as_list_files_dict(self):
        return dict(
            fileId=self.file_id,
            fileName=self.name,
            size=len(self.data_bytes),
            contentType=self.content_type,
            contentSha1=self.content_sha1,
            fileInfo=self.file_info,
            action=self.action,
            uploadTimestamp=self.upload_timestamp
        )

    def as_start_large_file_result(self):
        return dict(
            fileId=self.file_id,
            fileName=self.name,
            accountId=self.account_id,
            bucketId=self.bucket_id,
            contentType=self.content_type,
            fileInfo=self.file_info
        )

    def is_visible(self):
        """
        Does this file show up in b2_list_file_names?
        """
        return self.action == 'upload'


class BucketSimulator(object):
    def __init__(self, account_id, bucket_id, bucket_name, bucket_type):
        assert bucket_type in ['allPrivate', 'allPublic']
        self.account_id = account_id
        self.bucket_name = bucket_name
        self.bucket_id = bucket_id
        self.bucket_type = bucket_type
        self.upload_url_counter = iter(range(200))
        # File IDs count down, so that the most recent will come first when they are sorted.
        self.file_id_counter = iter(range(9999, 0, -1))
        self.file_id_to_file = dict()
        # It would be nice to use an OrderedDict for this, but 2.6 doesn't have it.
        self.file_name_and_id_to_file = dict()

    def bucket_json(self):
        return dict(
            accountId=self.account_id,
            bucketName=self.bucket_name,
            bucketId=self.bucket_id,
            bucketType=self.bucket_type
        )

    def download_file_by_name(self, file_name, download_dest):
        files = self.list_file_names(file_name, 1)['files']
        if len(files) == 0:
            raise FileNotPresent(file_name)
        file_dict = files[0]
        if file_dict['fileName'] != file_name or file_dict['action'] != 'upload':
            raise FileNotPresent(file_name)
        file_sim = self.file_name_and_id_to_file[(file_name, file_dict['fileId'])]
        with download_dest.open(
            file_sim.file_id, file_sim.name, file_sim.content_length, file_sim.content_type,
            file_sim.content_sha1, file_sim.file_info
        ) as f:
            f.write(file_sim.data_bytes)

    def get_upload_url(self):
        upload_id = six.next(self.upload_url_counter)
        upload_url = 'https://upload.example.com/%s/%s' % (self.bucket_id, upload_id)
        return dict(bucketId=self.bucket_id, uploadUrl=upload_url, authorizationToken=upload_url)

    def list_file_names(self, start_file_name=None, max_file_count=None):
        start_file_name = start_file_name or ''
        max_file_count = max_file_count or 100
        result_files = []
        next_file_name = None
        prev_file_name = None
        for key in sorted(six.iterkeys(self.file_name_and_id_to_file)):
            (file_name, file_id) = key
            if start_file_name <= file_name and file_name != prev_file_name:
                prev_file_name = file_name
                file = self.file_name_and_id_to_file[key]
                if file.is_visible():
                    result_files.append(file.as_list_files_dict())
                    if len(result_files) == max_file_count:
                        next_file_name = file.name + ' '
                        break
        return dict(files=result_files, nextFileName=next_file_name)

    def list_file_versions(self, start_file_name=None, start_file_id=None, max_file_count=None):
        start_file_name = start_file_name or ''
        start_file_id = start_file_id or ''
        max_file_count = max_file_count or 100
        result_files = []
        next_file_name = None
        next_file_id = None
        for key in sorted(six.iterkeys(self.file_name_and_id_to_file)):
            (file_name, file_id) = key
            if (start_file_name < file_name) or (
                start_file_name == file_name and start_file_id <= file_id
            ):
                file = self.file_name_and_id_to_file[key]
                result_files.append(file.as_list_files_dict())
                if len(result_files) == max_file_count:
                    next_file_name = file.name
                    next_file_id = str(int(file_id) + 1)
                    break
        return dict(files=result_files, nextFileName=next_file_name, nextFileId=next_file_id)

    def start_large_file(self, file_name, content_type, file_info):
        file_id = self._next_file_id()
        file = FileSimulator(
            self.account_id, self.bucket_id, file_id, 'upload', file_name, content_type, 'none',
            file_info, None
        )
        self.file_id_to_file[file_id] = file
        self.file_name_and_id_to_file[file.sort_key()] = file
        return file.as_start_large_file_result()

    def upload_file(
        self, upload_id, upload_auth_token, file_name, content_length, content_type, content_sha1,
        file_infos, data_stream
    ):
        data_bytes = data_stream.read()
        assert len(data_bytes) == content_length
        file_id = self._next_file_id()
        file = FileSimulator(
            self.account_id, self.bucket_id, file_id, 'upload', file_name, content_type,
            content_sha1, file_infos, data_bytes
        )
        self.file_id_to_file[file_id] = file
        self.file_name_and_id_to_file[file.sort_key()] = file
        return file.as_upload_result()

    def _next_file_id(self):
        return str(six.next(self.file_id_counter))


class RawSimulator(RawApi):
    """
    Implements the same interface as B2RawApi by simulating all of the
    calls and keeping state in memory.

    The intended use for this class is for unit tests that test things
    built on top of B2RawApi.
    """

    API_URL = 'http://api.example.com'
    DOWNLOAD_URL = 'http://download.example.com'

    MIN_PART_SIZE = 10000

    def __init__(self):
        self.authorized_accounts = set()
        self.bucket_name_to_bucket = dict()
        self.bucket_id_to_account = dict()
        self.bucket_id_to_bucket = dict()
        self.bucket_id_counter = iter(range(100))
        self.upload_errors = []

    def set_upload_errors(self, errors):
        """
        Stores a sequence of exceptions to raise on upload.  Each one will
        be raised in turn, until they are all gone.  Then the next upload
        will succeed.
        """
        assert len(self.upload_errors) == 0
        self.upload_errors = errors

    def authorize_account(self, _realm_url, account_id, _application_key):
        self.authorized_accounts.add(account_id)
        return dict(
            accountId=account_id,
            authorizationToken='AUTH:' + account_id,
            apiUrl=self.API_URL,
            downloadUrl=self.DOWNLOAD_URL,
            minimumPartSize=self.MIN_PART_SIZE
        )

    def create_bucket(self, api_url, account_auth_token, account_id, bucket_name, bucket_type):
        self._assert_account_auth(api_url, account_auth_token, account_id)
        if bucket_name in self.bucket_name_to_bucket:
            raise DuplicateBucketName(bucket_name)
        bucket_id = 'bucket_' + str(six.next(self.bucket_id_counter))
        bucket = BucketSimulator(account_id, bucket_id, bucket_name, bucket_type)
        self.bucket_name_to_bucket[bucket_name] = bucket
        self.bucket_id_to_account[bucket_id] = account_id
        self.bucket_id_to_bucket[bucket_id] = bucket
        return bucket.bucket_json()

    def download_file_by_id(self, download_url, account_auth_token_or_none, file_id, download_dest):
        url = download_url + '/b2api/v1/b2_download_file_by_id?fileId=' + file_id
        return self._download_file_from_url(url, account_auth_token_or_none, download_dest)

    def download_file_by_name(
        self, download_url, account_auth_token_or_none, bucket_name, file_name, download_dest
    ):
        assert download_url == self.DOWNLOAD_URL
        # TODO: check auth token if bucket is not public
        bucket = self._get_bucket_by_name(bucket_name)
        bucket.download_file_by_name(file_name, download_dest)

    def get_upload_url(self, api_url, account_auth_token, bucket_id):
        self._assert_account_auth(api_url, account_auth_token, self.bucket_id_to_account[bucket_id])
        return self._get_bucket_by_id(bucket_id).get_upload_url()

    def list_file_names(
        self,
        api_url,
        account_auth,
        bucket_id,
        start_file_name=None,
        max_file_count=None
    ):
        bucket = self._get_bucket_by_id(bucket_id)
        self._assert_account_auth(api_url, account_auth, bucket.account_id)
        return bucket.list_file_names(start_file_name, max_file_count)

    def list_file_versions(
        self,
        api_url,
        account_auth,
        bucket_id,
        start_file_name=None,
        start_file_id=None,
        max_file_count=None
    ):
        bucket = self._get_bucket_by_id(bucket_id)
        self._assert_account_auth(api_url, account_auth, bucket.account_id)
        return bucket.list_file_versions(start_file_name, start_file_id, max_file_count)

    def start_large_file(
        self, api_url, account_auth_token, bucket_id, file_name, content_type, file_info
    ):
        bucket = self._get_bucket_by_id(bucket_id)
        self._assert_account_auth(api_url, account_auth_token, bucket.account_id)
        return bucket.start_large_file(file_name, content_type, file_info)

    def upload_file(
        self, upload_url, upload_auth_token, file_name, content_length, content_type, content_sha1,
        file_infos, data_stream
    ):
        assert upload_url == upload_auth_token
        url_match = re.match(r'https://upload.example.com/([^/]*)/([^/]*)', upload_url)
        if url_match is None:
            raise BadUploadUrl(upload_url)
        if len(self.upload_errors) != 0:
            raise self.upload_errors.pop(0)
        bucket_id, upload_id = url_match.groups()
        return self._get_bucket_by_id(bucket_id).upload_file(
            upload_id, upload_auth_token, file_name, content_length, content_type, content_sha1,
            file_infos, data_stream
        )

    def _assert_account_auth(self, api_url, account_auth_token, account_id):
        assert api_url == self.API_URL
        assert account_auth_token == 'AUTH:' + account_id
        assert account_id in self.authorized_accounts

    def _get_bucket_by_id(self, bucket_id):
        if bucket_id not in self.bucket_id_to_bucket:
            raise NonExistentBucket(bucket_id)
        return self.bucket_id_to_bucket[bucket_id]

    def _get_bucket_by_name(self, bucket_name):
        if bucket_name not in self.bucket_name_to_bucket:
            raise NonExistentBucket(bucket_name)
        return self.bucket_name_to_bucket[bucket_name]
