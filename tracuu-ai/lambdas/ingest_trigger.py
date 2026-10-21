"""SQS (gom lô 60 giây từ EventBridge ← S3 Object Created) → bắt đầu một ingestion job cho cả lô.

Nếu Knowledge Base đang có job chạy, Bedrock trả ConflictException; ta ném lỗi để SQS giao lại
sau visibility timeout, tài liệu sẽ được gom vào lô kế tiếp.
"""
import json
import logging

from app.models import DocStatus
from app.services import pipeline

from ._common import services

log = logging.getLogger()
log.setLevel(logging.INFO)


def doc_ids_from_records(records):
    ids = []
    for r in records:
        detail = json.loads(r["body"]).get("detail", {})
        key = detail.get("object", {}).get("key", "")
        parts = key.split("/")
        # docs/{doc_id}/{tên tệp}; bỏ qua file .metadata.json
        if len(parts) == 3 and parts[0] == "docs" and not key.endswith(".metadata.json") and parts[1] not in ids:
            ids.append(parts[1])
    return ids


def handler(event, _context):
    s = services()
    ids = [i for i in doc_ids_from_records(event["Records"]) if s.store.get_doc(i)]
    if not ids:
        return {"started": 0}
    for i in ids:
        s.store.update_doc(i, status=DocStatus.UPLOADED)
    job_id = pipeline.start_batch(s.store, s.bedrock, ids)
    log.info("started ingestion job %s for %d docs", job_id, len(ids))
    return {"started": len(ids), "job_id": job_id}
