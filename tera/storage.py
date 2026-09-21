import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from tera.config import get_settings


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


def get_store():
    return ObjectStore()
