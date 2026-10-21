from flask import Blueprint, current_app, jsonify, request

from ..auth import require_admin
from ..services import pipeline
from ..services.documents import DocumentError
from ..services.rag import DEFAULT_KB_CONFIG

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

CHOICES = {"model": ("Claude Sonnet", "Claude Haiku", "Claude Opus"),
           "emb": ("Titan Text Embeddings V2", "Cohere Embed Multilingual"),
           "chunk": ("Theo ngữ nghĩa", "Kích thước cố định", "Phân cấp")}
RANGES = {"topk": (2, 20), "size": (128, 1024), "overlap": (0, 30)}
FLAGS = ("guard", "rerank", "pii")


def svc():
    return current_app.extensions["svc"]


def validate_config(body):
    """Trả về (cấu hình hợp lệ, lỗi). Chỉ nhận đúng các khoá đã biết."""
    out = {}
    for k in DEFAULT_KB_CONFIG:
        if k not in body:
            continue
        v = body[k]
        if k in CHOICES and v not in CHOICES[k]:
            return None, f"{k} không hợp lệ"
        if k in RANGES and not (isinstance(v, int) and not isinstance(v, bool) and RANGES[k][0] <= v <= RANGES[k][1]):
            return None, f"{k} phải là số nguyên trong khoảng {RANGES[k][0]}–{RANGES[k][1]}"
        if k in FLAGS and not isinstance(v, bool):
            return None, f"{k} phải là true/false"
        out[k] = v
    return out, None


@bp.get("/overview")
@require_admin
def overview():
    store = svc().store
    series = store.stat_series("queries", 28)
    up, down = sum(store.stat_series("feedback_up", 28)), sum(store.stat_series("feedback_down", 28))
    by_status = store.count_docs_by_status()
    return jsonify(
        queries_28d=sum(series), queries_by_day=series,
        docs_indexed=by_status.get("INDEXED", 0),
        docs_pending=sum(by_status.get(s, 0) for s in ("UPLOADING", "UPLOADED", "INGESTING")),
        docs_failed=by_status.get("FAILED", 0),
        helpful_pct=round(100 * up / (up + down)) if up + down else None, ratings=up + down,
        unanswered_28d=sum(store.stat_series("unanswered", 28)))


@bp.get("/kb-config")
@require_admin
def get_kb_config():
    return jsonify(svc().rag.kb_config())


@bp.put("/kb-config")
@require_admin
def put_kb_config():
    cfg, err = validate_config(request.get_json(silent=True) or {})
    if err:
        return jsonify(error=err), 400
    merged = {**svc().rag.kb_config(), **cfg}
    svc().store.put_config(merged)
    return jsonify(merged)


@bp.get("/groups")
@require_admin
def groups():
    return jsonify(items=svc().store.list_groups())


@bp.get("/jobs")
@require_admin
def jobs():
    return jsonify(items=[pipeline.job_to_json(j) for j in svc().store.list_jobs()])


@bp.post("/jobs")
@require_admin
def start_job():
    job_id = svc().docs.sync_now()
    return jsonify(id=job_id), 202


@bp.post("/documents/<doc_id>/retry")
@require_admin
def retry(doc_id):
    try:
        return jsonify(id=svc().docs.retry(doc_id)), 202
    except DocumentError as e:
        return jsonify(error=str(e)), e.status
