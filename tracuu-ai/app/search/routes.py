import json
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from ..auth import current_user, login_required
from ..services.store import VN_TZ

bp = Blueprint("search", __name__, url_prefix="/api")


def svc():
    return current_app.extensions["svc"]


def sse(events):
    for ev in events:
        yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"


def when_label(iso):
    t = datetime.fromisoformat(iso).astimezone(VN_TZ)
    today = datetime.now(VN_TZ).date()
    if t.date() == today:
        return f"Hôm nay, {t:%H:%M}"
    if t.date() == today - timedelta(days=1):
        return f"Hôm qua, {t:%H:%M}"
    return f"{t:%d/%m/%Y}"


def read_question():
    q = (request.get_json(silent=True) or {}).get("question") or (request.get_json(silent=True) or {}).get("query")
    max_len = current_app.config["CFG"].MAX_QUESTION_CHARS
    if not isinstance(q, str) or not 1 <= len(q.strip()) <= max_len:
        return None, (jsonify(error=f"Câu hỏi phải từ 1 đến {max_len} ký tự"), 400)
    if not current_app.extensions["limiter"].allow(current_user().id):
        return None, (jsonify(error="Bạn thao tác quá nhanh, hãy thử lại sau"), 429)
    return q.strip(), None


@bp.get("/me")
@login_required
def me():
    return jsonify(current_user().to_json())


@bp.post("/search")
@login_required
def search():
    q, err = read_question()
    if err:
        return err
    return jsonify(query=q, results=svc().rag.search(current_user(), q))


@bp.post("/ask")
@login_required
def ask():
    q, err = read_question()
    if err:
        return err
    user = current_user()  # nhóm lấy từ token đã xác thực, không nhận từ client
    body = request.get_json(silent=True) or {}
    events = svc().rag.ask(user, q, body.get("session_id"), save=body.get("save", True) is not False,
                          doc_id=body.get("doc_id") if isinstance(body.get("doc_id"), str) else None)
    return Response(stream_with_context(sse(events)), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/history")
@login_required
def history():
    items = svc().store.list_queries(current_user().id)
    return jsonify(items=[{"id": q["query_id"], "q": q["text"], "n": q["result_count"],
                           "when": when_label(q["created_at"])} for q in items])


@bp.delete("/history")
@login_required
def clear_history():
    svc().store.clear_queries(current_user().id)
    return "", 204


@bp.delete("/history/<query_id>")
@login_required
def delete_history(query_id):
    svc().store.delete_query(current_user().id, query_id)
    return "", 204


@bp.get("/chat/sessions")
@login_required
def sessions():
    return jsonify(items=[{"id": s["id"], "title": s["title"], "when": when_label(s["created_at"])}
                          for s in svc().store.list_sessions(current_user().id)])


@bp.get("/chat/sessions/<session_id>")
@login_required
def session_detail(session_id):
    msgs = svc().rag.session_messages(current_user(), session_id)
    return (jsonify(messages=msgs), 200) if msgs is not None else (jsonify(error="not_found"), 404)


@bp.post("/feedback")
@login_required
def feedback():
    body = request.get_json(silent=True) or {}
    rating = body.get("rating")
    if rating not in ("up", "down"):
        return jsonify(error="rating phải là up hoặc down"), 400
    user, store = current_user(), svc().store
    if not body.get("session_id") and not body.get("message_id"):  # phản hồi cho câu trả lời ở trang tìm kiếm
        store.incr_stat("feedback_" + rating)
        return "", 204
    if not store.get_session(user.id, str(body.get("session_id", ""))) or \
            not store.set_rating(body["session_id"], str(body.get("message_id", "")), rating):
        return jsonify(error="not_found"), 404
    store.incr_stat("feedback_" + rating)
    return "", 204
