import json
import time

from app import create_app
from tests.conftest import TestConfig


def parse_sse(resp):
    events = []
    for block in resp.get_data(as_text=True).strip().split("\n\n"):
        _, data = block.split("\n", 1)
        events.append(json.loads(data[len("data: "):]))
    return events


def test_me_dev_roles(client, staff):
    admin = client.get("/api/me").get_json()
    assert admin["role"] == "admin" and "Toàn công ty" in admin["groups"]
    assert client.get("/api/me", headers=staff).get_json()["role"] == "staff"


def test_search_never_returns_docs_outside_user_groups(client):
    ids = [r["id"] for r in client.post("/api/search", json={"query": "phạt vi phạm hợp đồng nhà cung cấp"}).get_json()["results"]]
    assert "d8" not in ids  # d8 chỉ cho Pháp chế + Mua sắm


def test_search_returns_scored_results_with_passage(client):
    res = client.post("/api/search", json={"query": "công tác phí"}).get_json()["results"]
    assert res[0]["id"] == "d1" and res[0]["passage"] and 0 < res[0]["score"] <= 1


def test_search_is_recorded_in_history(client):
    client.post("/api/search", json={"query": "nghỉ phép"})
    items = client.get("/api/history").get_json()["items"]
    assert items[0]["q"] == "nghỉ phép" and items[0]["when"].startswith("Hôm nay")
    client.delete(f"/api/history/{items[0]['id']}")
    assert all(i["q"] != "nghỉ phép" for i in client.get("/api/history").get_json()["items"])


def test_question_validation(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 400
    assert client.post("/api/ask", json={"question": "x" * 2001}).status_code == 400
    assert client.post("/api/search", json={}).status_code == 400


def test_rate_limit():
    cfg = type("C", (TestConfig,), {"RATE_LIMIT_PER_MIN": 2})
    c = create_app(cfg()).test_client()
    codes = [c.post("/api/search", json={"query": "phép"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_ask_streams_answer_with_citations_and_saves_session(client):
    resp = client.post("/api/ask", json={"question": "Mức công tác phí cho nhân viên là bao nhiêu?"})
    assert resp.mimetype == "text/event-stream"
    evs = parse_sse(resp)
    assert evs[0]["type"] == "meta" and evs[-1]["type"] == "done"
    text = "".join(e["text"] for e in evs if e["type"] == "delta")
    assert "350.000" in text and "[1]" in text
    docs = next(e for e in evs if e["type"] == "citations")["docs"]
    assert docs[0]["id"] == "d1"

    sid = evs[0]["session_id"]
    msgs = client.get(f"/api/chat/sessions/{sid}").get_json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["docs"][0]["id"] == "d1"
    assert client.get("/api/chat/sessions").get_json()["items"][0]["id"] == sid


def test_ask_with_save_false_leaves_no_session_and_feedback_still_counts(client):
    evs = parse_sse(client.post("/api/ask", json={"question": "nghỉ phép", "save": False}))
    assert evs[0] == {"type": "meta", "session_id": None} and evs[-1]["message_id"] is None
    assert client.get("/api/chat/sessions").get_json()["items"] == []
    assert client.post("/api/feedback", json={"rating": "down"}).status_code == 204
    assert client.get("/api/admin/overview").get_json()["helpful_pct"] == 0


def test_ask_scoped_to_one_document(client, staff):
    evs = parse_sse(client.post("/api/ask", json={"question": "Tài liệu này nói gì?", "doc_id": "d1"}))
    assert next(e for e in evs if e["type"] == "citations")["docs"][0]["id"] == "d1"
    # tài liệu ngoài quyền không được dùng làm phạm vi
    evs = parse_sse(client.post("/api/ask", json={"question": "nói gì?", "doc_id": "d8"}, headers=staff))
    assert evs == [{"type": "error", "message": "Không tìm thấy tài liệu"}]


def test_download_requires_access_and_is_unavailable_locally(client):
    assert client.get("/api/documents/d8/download").status_code == 404
    assert client.get("/api/documents/d1/download").status_code == 409  # dữ liệu mẫu không có tệp gốc


def test_ask_without_permission_does_not_leak_documents(client, staff):
    # d8 (hợp đồng khung) chỉ dành cho Pháp chế/Mua sắm: người dùng này không có quyền
    evs = parse_sse(client.post("/api/ask", json={"question": "Quy trình mua sắm nhà cung cấp trên 200 triệu"}, headers=staff))
    cited = next(e for e in evs if e["type"] == "citations")["docs"]
    assert all(d["id"] != "d8" for d in cited)


def test_unknown_session_is_404(client):
    assert client.get("/api/chat/sessions/khong-co").status_code == 404
    evs = parse_sse(client.post("/api/ask", json={"question": "nghỉ phép", "session_id": "khong-co"}))
    assert evs == [{"type": "error", "message": "Không tìm thấy phiên hội thoại"}]


def test_feedback(client):
    evs = parse_sse(client.post("/api/ask", json={"question": "nghỉ phép"}))
    sid, mid = evs[0]["session_id"], evs[-1]["message_id"]
    assert client.post("/api/feedback", json={"session_id": sid, "message_id": mid, "rating": "up"}).status_code == 204
    assert client.post("/api/feedback", json={"session_id": sid, "message_id": mid, "rating": "meh"}).status_code == 400
    assert client.post("/api/feedback", json={"session_id": sid, "message_id": "x", "rating": "up"}).status_code == 404
    assert client.get("/api/admin/overview").get_json()["helpful_pct"] == 100


def test_documents_visibility(client):
    ids = [d["id"] for d in client.get("/api/documents").get_json()["items"]]
    assert "d8" not in ids and "d1" in ids
    assert client.get("/api/documents/d8").status_code == 404  # không lộ sự tồn tại
    assert client.get("/api/documents?dept=Nhân sự").get_json()["items"][0]["dept"] == "Nhân sự"


def test_summarize_requires_access_and_returns_bullets(client):
    assert len(client.post("/api/documents/d1/summarize").get_json()["summary"]) == 4
    assert client.post("/api/documents/d8/summarize").status_code == 404


def test_upload_flow_validates_and_progresses(app, client):
    assert client.post("/api/uploads", json={"filename": "virus.exe", "size": 10}).status_code == 400
    assert client.post("/api/uploads", json={"filename": "a.pdf", "size": 51 * 1024 * 1024}).status_code == 400
    # nhân viên không được chia sẻ cho nhóm mình không thuộc
    r = client.post("/api/uploads", json={"filename": "a.pdf", "size": 100, "groups": ["Pháp chế"]},
                    headers={"X-Dev-Role": "staff"})
    assert r.status_code == 403

    r = client.post("/api/uploads", json={"filename": "../../Báo cáo.pdf", "size": 2048, "groups": ["Tài chính"], "dept": "Tài chính"})
    assert r.status_code == 201
    body = r.get_json()
    doc_id = body["doc"]["id"]
    assert body["doc"]["title"] == "Báo cáo" and body["doc"]["status"] == "UPLOADING"  # tên tệp được làm sạch
    meta = app.extensions["svc"].storage.metadata[f"docs/{doc_id}/Báo cáo.pdf"]
    from app.services.acl import group_key
    assert meta == {"doc_id": doc_id, group_key("Tài chính"): True}  # chỉ cờ nhóm được chọn, không cờ nhóm khác

    assert client.get(f"/api/documents/{doc_id}/status").get_json() == {"status": "UPLOADING", "stage": 0}
    assert client.put(body["upload_url"], data=b"%PDF").status_code == 200
    for _ in range(40):
        st = client.get(f"/api/documents/{doc_id}/status").get_json()
        if st["status"] == "INDEXED":
            break
        time.sleep(0.2)
    assert st == {"status": "INDEXED", "stage": 3}


def test_delete_document_only_by_owner_or_admin(client):
    up = client.post("/api/uploads", json={"filename": "x.pdf", "size": 10, "groups": ["Tài chính"]}).get_json()
    assert client.delete(f"/api/documents/{up['doc']['id']}").status_code == 204
    assert client.get(f"/api/documents/{up['doc']['id']}").status_code == 404
    # d1 không do người dùng staff tải lên
    assert client.delete("/api/documents/d1", headers={"X-Dev-Role": "staff"}).status_code == 403


def test_admin_endpoints_forbidden_for_staff(client, staff):
    for method, url in [("get", "/api/admin/overview"), ("get", "/api/admin/kb-config"), ("put", "/api/admin/kb-config"),
                        ("get", "/api/admin/groups"), ("get", "/api/admin/jobs"), ("post", "/api/admin/jobs")]:
        assert getattr(client, method)(url, headers=staff).status_code == 403, url


def test_kb_config_validation_and_roundtrip(client):
    assert client.put("/api/admin/kb-config", json={"topk": 99}).status_code == 400
    assert client.put("/api/admin/kb-config", json={"guard": "yes"}).status_code == 400
    assert client.put("/api/admin/kb-config", json={"model": "GPT"}).status_code == 400
    assert client.put("/api/admin/kb-config", json={"topk": 8, "guard": False, "evil": 1}).get_json()["topk"] == 8
    cfg = client.get("/api/admin/kb-config").get_json()
    assert cfg["topk"] == 8 and cfg["guard"] is False and "evil" not in cfg


def test_admin_overview_groups_jobs(client):
    ov = client.get("/api/admin/overview").get_json()
    assert ov["docs_indexed"] == 8 and len(ov["queries_by_day"]) == 28
    assert {g["name"] for g in client.get("/api/admin/groups").get_json()["items"]} >= {"Tài chính", "Pháp chế"}
    jobs = client.get("/api/admin/jobs").get_json()["items"]
    assert jobs[0]["status"] in ("COMPLETE", "FAILED")
    assert client.post("/api/admin/jobs").status_code == 202
    assert client.get("/api/admin/jobs").get_json()["items"][0]["status"] == "IN_PROGRESS"


def test_healthz_and_unknown_api(client):
    assert client.get("/healthz").data == b"ok"
    assert client.get("/api/nope").status_code == 404


def test_refuses_dev_auth_with_real_aws_backend():
    import pytest
    cfg = type("C", (TestConfig,), {"BACKEND": "aws", "AUTH_MODE": "dev"})
    with pytest.raises(RuntimeError):
        create_app(cfg())
