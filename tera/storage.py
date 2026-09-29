from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from tera.config import get_settings


class StorageError(RuntimeError):
    pass


class ObjectStore:
    def __init__(self, settings=None):
        settings = settings or get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )

    def ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as create_error:
                if create_error.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

    def check_health(self):
        self.client.head_bucket(Bucket=self.bucket)

    def put(self, key, data):
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType="application/pdf"
        )

    def read(self, key):
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


class LocalObjectStore:
    def __init__(self, settings=None):
        settings = settings or get_settings()
        self.root = Path(settings.local_storage_path).resolve()

    def _path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("Invalid storage key")
        return path

    def ensure_bucket(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Local document storage unavailable") from exc

    def check_health(self):
        self.ensure_bucket()

    def put(self, key, data):
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError("Could not write document") from exc

    def read(self, key):
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError("Could not read document") from exc

    def delete(self, key):
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Could not delete document") from exc


def get_store():
    settings = get_settings()
    return (
        LocalObjectStore(settings) if settings.storage_backend == "local" else ObjectStore(settings)
    )
