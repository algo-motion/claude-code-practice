import threading

from flask import Blueprint, current_app, jsonify, request

from ..auth import current_user, login_required
from ..models import DocStatus, doc_to_json
from ..services import pipeline
from ..services.documents import DocumentError

bp = Blueprint("library", __name__, url_prefix="/api")

# Giai đoạn hiển thị ở UI: tải lên → trích xuất → embedding → đã lập chỉ mục
STAGE = {DocStatus.UPLOADING: 0, DocStatus.UPLOADED: 1, DocStatus.INGESTING: 2, DocStatus.INDEXED: 3}


def svc():
    return current_app.extensions["svc"]


@bp.errorhandler(DocumentError)
def doc_error(e):
    return jsonify(error=str(e)), e.status


@bp.get("/documents")
@login_required
def list_documents():
    return jsonify(items=svc().docs.list(current_user(), request.args.get("dept") or None))


@bp.get("/documents/<doc_id>")
@login_required
def get_document(doc_id):
    doc = svc().docs.get(current_user(), doc_id)
    return (jsonify(doc_to_json(doc)), 200) if doc else (jsonify(error="not_found"), 404)


@bp.get("/documents/<doc_id>/status")
@login_required
def document_status(doc_id):
    doc = svc().docs.get(current_user(), doc_id)
    if not doc:
        return jsonify(error="not_found"), 404
    return jsonify(status=doc["status"], stage=STAGE.get(doc["status"], 0))


@bp.post("/documents/<doc_id>/summarize")
@login_required
def summarize(doc_id):
    summary = svc().docs.summarize(current_user(), doc_id)
    return (jsonify(summary=summary), 200) if summary is not None else (jsonify(error="not_found"), 404)


@bp.get("/documents/<doc_id>/download")
@login_required
def download(doc_id):
    url = svc().docs.download_url(current_user(), doc_id)
    return (jsonify(url=url), 200) if url else (jsonify(error="not_found"), 404)


@bp.delete("/documents/<doc_id>")
@login_required
def delete_document(doc_id):
    return ("", 204) if svc().docs.delete(current_user(), doc_id) else (jsonify(error="not_found"), 404)


@bp.post("/uploads")
@login_required
def create_upload():
    body = request.get_json(silent=True) or {}
    size = body.get("size")
    if not isinstance(size, int) or not isinstance(body.get("filename"), str):
        return jsonify(error="Thiếu filename hoặc size"), 400
    groups = body.get("groups") if isinstance(body.get("groups"), list) else None
    return jsonify(svc().docs.create_upload(current_user(), body["filename"], size, groups, body.get("dept"))), 201


def register_local_upload(app, step=1.4):
    """Chế độ local: thay S3 + EventBridge + Lambda bằng một endpoint PUT và vài timer."""

    @app.put("/api/_local/upload/<doc_id>")
    @login_required
    def local_upload(doc_id):
        s = app.extensions["svc"]
        doc = s.docs.get(current_user(), doc_id)
        if not doc or doc["status"] != DocStatus.UPLOADING:
            return jsonify(error="not_found"), 404
        s.store.update_doc(doc_id, status=DocStatus.UPLOADED)

        def ingest():
            pipeline.start_batch(s.store, s.bedrock, [doc_id])
            threading.Timer(step, lambda: pipeline.poll_jobs(s.store, s.bedrock)).start()

        threading.Timer(step, ingest).start()
        return "", 200
