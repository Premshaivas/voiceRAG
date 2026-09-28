from __future__ import annotations

from typing import Any

import boto3
from botocore.client import BaseClient

from .config import Settings, settings


class ObjectStorage:
    def __init__(self, active_settings: Settings = settings, client: BaseClient | None = None):
        self.settings = active_settings
        self.client = client or boto3.client("s3", endpoint_url=active_settings.s3_endpoint_url, region_name=active_settings.s3_region, aws_access_key_id=active_settings.s3_access_key, aws_secret_access_key=active_settings.s3_secret_key)

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.s3_bucket)
        except self.client.exceptions.ClientError:
            self.client.create_bucket(Bucket=self.settings.s3_bucket)

    def presigned_put(self, object_key: str, content_type: str) -> str:
        return self.client.generate_presigned_url("put_object", Params={"Bucket": self.settings.s3_bucket, "Key": object_key, "ContentType": content_type}, ExpiresIn=self.settings.s3_presign_seconds)

    def create_multipart(self, object_key: str, content_type: str) -> str:
        result = self.client.create_multipart_upload(Bucket=self.settings.s3_bucket, Key=object_key, ContentType=content_type)
        return result["UploadId"]

    def presigned_part(self, object_key: str, upload_id: str, part_number: int) -> str:
        return self.client.generate_presigned_url("upload_part", Params={"Bucket": self.settings.s3_bucket, "Key": object_key, "UploadId": upload_id, "PartNumber": part_number}, ExpiresIn=self.settings.s3_presign_seconds)

    def presigned_get(self, object_key: str, content_type: str | None = None) -> str:
        params: dict[str, Any] = {"Bucket": self.settings.s3_bucket, "Key": object_key}
        if content_type:
            params["ResponseContentType"] = content_type
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=self.settings.s3_presign_seconds)

    def complete_multipart(self, object_key: str, upload_id: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
        return self.client.complete_multipart_upload(Bucket=self.settings.s3_bucket, Key=object_key, UploadId=upload_id, MultipartUpload={"Parts": sorted(parts, key=lambda p: p["PartNumber"])})

    def abort_multipart(self, object_key: str, upload_id: str) -> None:
        self.client.abort_multipart_upload(Bucket=self.settings.s3_bucket, Key=object_key, UploadId=upload_id)

    def download(self, object_key: str, destination: str) -> None:
        self.client.download_file(self.settings.s3_bucket, object_key, destination)

    def head(self, object_key: str) -> dict[str, Any]:
        return self.client.head_object(Bucket=self.settings.s3_bucket, Key=object_key)
