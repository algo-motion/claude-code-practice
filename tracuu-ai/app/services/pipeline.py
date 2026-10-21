"""Logic nạp tài liệu dùng chung cho Lambda (lambdas/*.py), endpoint quản trị và mô phỏng local.

Vòng đời tài liệu: UPLOADING -> UPLOADED -> INGESTING -> INDEXED | FAILED
"""
from datetime import datetime, timezone

from ..models import DocStatus
from .store import VN_TZ, now_iso


def start_batch(store, bedrock, doc_ids):
    """Bắt đầu một ingestion job cho cả lô tài liệu và gắn job_id vào từng tài liệu."""
    job_id = bedrock.start_ingestion()
    store.put_job({"job_id": job_id, "status": "IN_PROGRESS", "started_at": now_iso(),
                   "doc_count": len(doc_ids), "doc_ids": list(doc_ids)})
    for did in doc_ids:
        store.update_doc(did, status=DocStatus.INGESTING, job_id=job_id)
    return job_id


def poll_jobs(store, bedrock, enqueue_summary=lambda doc_id: None):
    """Cập nhật các job đang chạy. Trả về số job đã kết thúc."""
    finished = 0
    for job in store.list_jobs("IN_PROGRESS"):
        r = bedrock.get_ingestion_job(job["job_id"])
        if r["status"] == "IN_PROGRESS":
            continue
        ok = r["status"] == "COMPLETE"
        store.update_job(job["job_id"], status="COMPLETE" if ok else "FAILED", ended_at=now_iso())
        for did in job.get("doc_ids", []):
            store.update_doc(did, status=DocStatus.INDEXED if ok else DocStatus.FAILED)
            if ok:
                enqueue_summary(did)
        finished += 1
    return finished


def duration_label(job):
    try:
        a = datetime.fromisoformat(job["started_at"])
        b = datetime.fromisoformat(job["ended_at"]) if job.get("ended_at") else None
    except (KeyError, ValueError):
        return job.get("duration", "—")
    if not b:
        return "…"
    s = int((b - a).total_seconds())
    return f"{s // 60} ph {s % 60} s" if s >= 60 else f"{s} s"


def job_to_json(job):
    started = job.get("started_at", "")
    try:
        started = datetime.fromisoformat(started).astimezone(VN_TZ).strftime("%H:%M")
    except ValueError:
        pass  # dữ liệu mẫu đã là nhãn như "Hôm qua"
    return {"id": job["job_id"], "source": job.get("source", "s3://docs/"), "started": started,
            "docs": job.get("doc_count", 0), "status": job["status"], "duration": duration_label(job)}
