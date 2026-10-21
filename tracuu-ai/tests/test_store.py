def doc(i, groups, **kw):
    return {"id": i, "title": f"Tài liệu {i}", "type": "PDF", "dept": "Tài chính", "groups": groups,
            "status": "INDEXED", "updated_at": f"2026-09-0{i}", "pages": 3, **kw}


def test_docs_filtered_by_group_and_dept(store):
    store.put_doc(doc("1", ["A"]))
    store.put_doc(doc("2", ["B"], dept="Nhân sự"))
    store.put_doc(doc("3", ["A", "B"]))
    assert [d["id"] for d in store.list_docs(["A"])] == ["3", "1"]  # mới nhất trước, không trùng
    assert [d["id"] for d in store.list_docs(["A", "B"])] == ["3", "2", "1"]
    assert [d["id"] for d in store.list_docs(["B"], dept="Nhân sự")] == ["2"]
    assert store.list_docs(["C"]) == []


def test_hidden_statuses_not_listed(store):
    store.put_doc(doc("1", ["A"]))
    store.update_doc("1", status="DELETED")
    assert store.list_docs(["A"]) == []
    assert store.get_doc("1")["status"] == "DELETED"


def test_numbers_come_back_as_python_numbers(store):
    store.put_doc(doc("1", ["A"]))
    assert store.get_doc("1")["pages"] == 3 and isinstance(store.get_doc("1")["pages"], int)


def test_jobs_by_status(store):
    store.put_job({"job_id": "j1", "status": "IN_PROGRESS", "started_at": "2026-10-01T10:00:00+00:00", "doc_count": 2})
    store.put_job({"job_id": "j2", "status": "COMPLETE", "started_at": "2026-10-01T09:00:00+00:00", "doc_count": 1})
    assert [j["job_id"] for j in store.list_jobs("IN_PROGRESS")] == ["j1"]
    store.update_job("j1", status="COMPLETE")
    assert store.list_jobs("IN_PROGRESS") == []
    assert [j["job_id"] for j in store.list_jobs()] == ["j1", "j2"]


def test_chat_sessions_are_private_and_ordered(store):
    s1 = store.create_session("u1", "Câu hỏi 1")
    s2 = store.create_session("u1", "Câu hỏi 2")
    assert store.get_session("u2", s1["id"]) is None
    assert [s["id"] for s in store.list_sessions("u1")] == [s2["id"], s1["id"]]
    store.update_session("u1", s1["id"], bedrock_session_id="b-1")
    assert store.get_session("u1", s1["id"])["bedrock_session_id"] == "b-1"


def test_messages_and_rating(store):
    s = store.create_session("u1", "x")
    store.append_message(s["id"], "user", "hỏi")
    m = store.append_message(s["id"], "assistant", "đáp", [{"doc_id": "1", "page": 2, "excerpt": "e"}])
    msgs = store.list_messages(s["id"])
    assert [x["role"] for x in msgs] == ["user", "assistant"]
    assert msgs[1]["citations"][0]["page"] == 2
    assert store.set_rating(s["id"], m["message_id"], "up") is True
    assert store.set_rating(s["id"], "không-tồn-tại", "up") is False
    assert store.list_messages(s["id"])[1]["rating"] == "up"


def test_search_history(store):
    a = store.add_query("u1", "một", 3)
    store.add_query("u1", "hai", 1)
    store.add_query("u2", "của người khác", 1)
    assert [q["text"] for q in store.list_queries("u1")] == ["hai", "một"]
    store.delete_query("u1", a["query_id"])
    assert [q["text"] for q in store.list_queries("u1")] == ["hai"]
    store.clear_queries("u1")
    assert store.list_queries("u1") == [] and len(store.list_queries("u2")) == 1


def test_stats_counters(store):
    store.incr_stat("queries")
    store.incr_stat("queries", 2)
    series = store.stat_series("queries", 28)
    assert len(series) == 28 and series[-1] == 3 and sum(series) == 3


def test_config_roundtrip(store):
    assert store.get_config() is None
    store.put_config({"topk": 8, "guard": False})
    assert store.get_config() == {"topk": 8, "guard": False}
