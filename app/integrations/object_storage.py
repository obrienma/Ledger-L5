from typing import Protocol

import boto3

from app.config import settings


class ObjectStorageClient(Protocol):
    def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    def download(self, key: str) -> bytes: ...


class R2Client:
    """Same shape as StripeClient (app/integrations/stripe.py) — an isolated
    outbound client. Wraps boto3's S3 client pointed at Cloudflare R2's
    S3-compatible endpoint rather than AWS's (ADR 0015); R2 speaks the same
    API, so nothing beyond the endpoint URL and credentials differs from a
    real S3 client."""

    def __init__(
        self,
        account_id: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        bucket_name: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name or settings.r2_bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id or settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id or settings.r2_access_key_id,
            aws_secret_access_key=secret_access_key or settings.r2_secret_access_key,
            region_name="auto",
        )

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self.bucket_name, Key=key, Body=data, ContentType=content_type
        )

    def download(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()
