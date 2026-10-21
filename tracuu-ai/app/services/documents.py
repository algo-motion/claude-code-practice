import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePath

from ..models import DocStatus, doc_to_json
from .acl import metadata_attributes
from .storage import doc_key
from .store import now_iso
from . import pipeline

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
}


class DocumentError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def human_size(n):
    return f"{n / 1048576:.1f} MB".replace(".", ",") if n >= 1048576 else f"{max(n // 1024, 1)} KB"


class DocumentService:
    def __init__(self, cfg, store, bedrock, storage):
        self.cfg, self.store, self.bedrock, self.storage = cfg, store, bedrock, storage

    def _visible(self, user, doc):
        return bool(doc) and doc.get("status") not in ("DELETED", "EXPIRED") \
            and bool(set(doc.get("groups", [])) & set(user.groups))

    def _expire_if_stale(self, doc):
        """Bản ghi UPLOADING quá hạn presigned URL thì coi như EXPIRED."""
        if doc.get("status") == DocStatus.UPLOADING and doc.get("created_at"):
            age = datetime.now(timezone.utc) - datetime.fromisoformat(doc["created_at"])
            if age > timedelta(seconds=self.cfg.UPLOAD_URL_TTL):
                self.store.update_doc(doc["id"], status=DocStatus.EXPIRED)
                doc["status"] = DocStatus.EXPIRED
        return doc

    def list(self, user, dept=None):
        docs = [self._expire_if_stale(d) for d in self.store.list_docs(user.groups, dept)]
        return [doc_to_json(d) for d in docs if d["status"] != DocStatus.EXPIRED]

    def get(self, user, doc_id):
        """Trả None cả khi tài liệu không tồn tại lẫn khi người dùng không có quyền (không lộ sự tồn tại)."""
        doc = self.store.get_doc(doc_id)
        return self._expire_if_stale(doc) if self._visible(user, doc) else None

    def create_upload(self, user, filename, size, groups, dept):
        name = PurePath(filename or "").name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in self.cfg.ALLOWED_EXT:
            raise DocumentError("Loại tệp không được hỗ trợ")
        if not 0 < size <= self.cfg.MAX_UPLOAD_BYTES:
            raise DocumentError("Tệp rỗng hoặc vượt quá 50 MB")
        groups = list(dict.fromkeys(groups or [self.cfg.ALL_STAFF_GROUP]))
        if not user.is_admin and not set(groups) <= set(user.groups):
            raise DocumentError("Bạn chỉ được chia sẻ cho nhóm của mình", 403)

        doc_id = uuid.uuid4().hex[:12]
        key = doc_key(doc_id, name)
        now = now_iso()
        doc = {"id": doc_id, "title": name.rsplit(".", 1)[0], "type": ext.upper() if ext in ("pdf", "docx", "xlsx") else "PDF",
               "dept": dept or "—", "groups": groups, "pages": 0, "size": human_size(size), "owner": user.name,
               "owner_id": user.id, "status": DocStatus.UPLOADING, "s3_key": key, "created_at": now, "updated_at": now[:10]}
        self.store.put_doc(doc)
        self.storage.put_metadata(key, metadata_attributes(doc_id, groups))
        ctype = CONTENT_TYPES[ext]
        return {"doc": doc_to_json(doc), "upload_url": self.storage.presign_put(key, ctype), "content_type": ctype}

    def summarize(self, user, doc_id):
        doc = self.get(user, doc_id)
        if not doc:
            return None
        if doc.get("status") != DocStatus.INDEXED:
            raise DocumentError("Tài liệu chưa được lập chỉ mục", 409)
        if not doc.get("summary"):
            doc["summary"] = self.bedrock.summarize(doc_id)
            self.store.update_doc(doc_id, summary=doc["summary"])
        return doc["summary"]

    def download_url(self, user, doc_id):
        doc = self.get(user, doc_id)
        if not doc:
            return None
        if not doc.get("s3_key") or doc.get("status") != DocStatus.INDEXED:
            raise DocumentError("Tệp gốc chưa khả dụng", 409)
        url = self.storage.presign_get(doc["s3_key"], PurePath(doc["s3_key"]).name)
        if not url:
            raise DocumentError("Chế độ local không có tệp gốc để tải", 501)
        return url

    def delete(self, user, doc_id):
        doc = self.get(user, doc_id)
        if not doc:
            return False
        if not (user.is_admin or doc.get("owner_id") == user.id):
            raise DocumentError("Chỉ người tải lên hoặc quản trị viên được xoá", 403)
        self.store.update_doc(doc_id, status=DocStatus.DELETED)
        if doc.get("s3_key"):
            self.storage.delete(doc["s3_key"])  # lần đồng bộ KB tiếp theo sẽ gỡ khỏi index
        return True

    def retry(self, doc_id):
        doc = self.store.get_doc(doc_id)
        if not doc or doc["status"] != DocStatus.FAILED:
            raise DocumentError("Chỉ thử lại được tài liệu bị lỗi", 409)
        return pipeline.start_batch(self.store, self.bedrock, [doc_id])

    def sync_now(self):
        """Quản trị viên bấm 'Đồng bộ ngay': chạy một ingestion job cho toàn data source."""
        job_id = self.bedrock.start_ingestion()
        self.store.put_job({"job_id": job_id, "status": "IN_PROGRESS", "started_at": now_iso(),
                            "doc_count": 0, "doc_ids": [], "source": f"s3://{self.cfg.DOCS_BUCKET or 'docs'}/"})
        return job_id
