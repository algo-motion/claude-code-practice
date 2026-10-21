"""Kho tệp tài liệu: S3 (presigned URL + file .metadata.json cho Knowledge Base) hoặc giả lập local."""
import json
from urllib.parse import quote

import boto3
from botocore.config import Config


def doc_key(doc_id, filename):
    return f"docs/{doc_id}/{filename}"


class S3Storage:
    def __init__(self, cfg, client=None):
        self.bucket = cfg.DOCS_BUCKET
        self.ttl = cfg.UPLOAD_URL_TTL
        # SigV4 để presigned URL hoạt động với bucket mã hoá SSE-KMS.
        self.s3 = client or boto3.client("s3", region_name=cfg.AWS_REGION, config=Config(signature_version="s3v4"))

    def presign_put(self, key, content_type):
        return self.s3.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type}, ExpiresIn=self.ttl)

    def presign_get(self, key, filename):
        return self.s3.generate_presigned_url(
            "get_object", ExpiresIn=self.ttl,
            Params={"Bucket": self.bucket, "Key": key,
                    "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(filename)}"})

    def put_metadata(self, key, attrs):
        """Knowledge Base đọc <tệp>.metadata.json cạnh tài liệu để lọc theo nhóm (xem acl.py)."""
        self.s3.put_object(Bucket=self.bucket, Key=key + ".metadata.json", ContentType="application/json",
                           Body=json.dumps({"metadataAttributes": attrs}, ensure_ascii=False).encode())

    def delete(self, key):
        self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": key}, {"Key": key + ".metadata.json"}]})


class LocalStorage:
    def __init__(self):
        self.metadata = {}

    def presign_put(self, key, content_type):
        doc_id = key.split("/")[1]
        return f"/api/_local/upload/{doc_id}"

    def presign_get(self, key, filename):
        return None  # chế độ local không lưu tệp gốc

    def put_metadata(self, key, attrs):
        self.metadata[key] = attrs

    def delete(self, key):
        self.metadata.pop(key, None)
