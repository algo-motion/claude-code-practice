"""AwsBedrock với client giả: kiểm tra tham số gửi đi và cách đọc stream, không gọi AWS."""
import pytest
from botocore.exceptions import ClientError

from app.config import Config
from app.services.acl import group_key
from app.services.bedrock import AwsBedrock, doc_id_from_uri, group_filter


class FakeRuntime:
    def __init__(self, events=(), fail=0):
        self.events, self.fail, self.calls = list(events), fail, []

    def retrieve_and_generate_stream(self, **kw):
        self.calls.append(kw)
        if self.fail:
            self.fail -= 1
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "RetrieveAndGenerateStream")
        return {"stream": iter(self.events), "sessionId": "bsess-1"}

    def retrieve(self, **kw):
        self.calls.append(kw)
        return {"retrievalResults": [
            {"content": {"text": "đoạn A"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://b/docs/d1/quy-che.pdf"}},
             "metadata": {"x-amz-bedrock-kb-document-page-number": 14}},
            {"content": {"text": "đoạn B"}, "score": 0.5, "location": {"s3Location": {"uri": "s3://b/docs/d2/x.docx"}},
             "metadata": {"doc_id": "d2"}}]}


def cfg():
    c = Config()
    c.KB_ID, c.MODEL_ARN, c.GUARDRAIL_ID = "KB1", "arn:model", "gr-1"
    return c


def ref(uri, text="trích"):
    return {"content": {"text": text}, "location": {"s3Location": {"uri": uri}}, "metadata": {}}


def test_group_filter_shapes():
    assert group_filter(["A"]) == {"equals": {"key": group_key("A"), "value": True}}
    assert group_filter(["A", "B"])["orAll"][1] == {"equals": {"key": group_key("B"), "value": True}}
    assert "__no_group__" in str(group_filter([]))  # không nhóm => không thấy gì, không phải thấy tất cả
    assert "listContains" not in str(group_filter(["A", "B"]))  # chỉ OpenSearch hỗ trợ toán tử này


def test_group_key_is_stable_ascii_and_distinct_for_vietnamese_names():
    assert group_key("Tài chính") == group_key("Tài chính") != group_key("Tai chinh")
    assert group_key("Tài chính").isascii() and group_key("Tài chính").startswith("g_")


def test_doc_id_from_uri():
    assert doc_id_from_uri("s3://b/docs/abc123/Báo cáo.pdf") == "abc123"


def test_search_maps_hits_and_applies_filter():
    rt = FakeRuntime()
    hits = AwsBedrock(cfg(), agent_rt=rt, agent=None).search(["Tài chính", "Admin"], "hỏi", 4)
    assert [h["doc_id"] for h in hits] == ["d1", "d2"] and hits[0]["page"] == 14
    vs = rt.calls[0]["retrievalConfiguration"]["vectorSearchConfiguration"]
    assert vs["numberOfResults"] == 4 and vs["overrideSearchType"] == "SEMANTIC" and "orAll" in vs["filter"]


def test_ask_stream_inserts_citation_markers_in_order_of_first_use():
    events = [{"output": {"text": "Mức khoán 350k"}},
              {"citation": {"retrievedReferences": [ref("s3://b/docs/d1/a.pdf")]}},
              {"output": {"text": " và hạn 10 ngày"}},
              {"citation": {"retrievedReferences": [ref("s3://b/docs/d3/b.pdf"), ref("s3://b/docs/d1/a.pdf")]}}]
    rt = FakeRuntime(events)
    out = list(AwsBedrock(cfg(), agent_rt=rt).ask_stream(["G"], "hỏi", session_id="prev"))
    text = "".join(e["text"] for e in out if e["type"] == "delta")
    assert text == "Mức khoán 350k [1] và hạn 10 ngày [2][1]"
    cites = next(e for e in out if e["type"] == "citations")["items"]
    assert [c["doc_id"] for c in cites] == ["d1", "d3"]
    assert out[-1] == {"type": "session", "id": "bsess-1"}
    p = rt.calls[0]
    assert p["sessionId"] == "prev"
    gen = p["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]["generationConfiguration"]
    assert gen["guardrailConfiguration"]["guardrailId"] == "gr-1"


def test_search_type_can_be_switched_for_opensearch_or_left_to_bedrock_default():
    c = cfg()
    c.SEARCH_TYPE = "HYBRID"
    rt = FakeRuntime()
    AwsBedrock(c, agent_rt=rt).search(["G"], "q")
    assert rt.calls[0]["retrievalConfiguration"]["vectorSearchConfiguration"]["overrideSearchType"] == "HYBRID"
    c.SEARCH_TYPE = "DEFAULT"
    rt = FakeRuntime()
    AwsBedrock(c, agent_rt=rt).search(["G"], "q")
    assert "overrideSearchType" not in rt.calls[0]["retrievalConfiguration"]["vectorSearchConfiguration"]


def test_scope_to_single_document_adds_doc_id_condition():
    rt = FakeRuntime([])
    list(AwsBedrock(cfg(), agent_rt=rt).ask_stream(["G"], "hỏi", doc_id="d9"))
    flt = rt.calls[0]["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]["retrievalConfiguration"][
        "vectorSearchConfiguration"]["filter"]
    assert flt == {"andAll": [group_filter(["G"]), {"equals": {"key": "doc_id", "value": "d9"}}]}


def test_ask_stream_guardrail_blocks():
    rt = FakeRuntime([{"output": {"text": "bị chặn một phần"}}, {"guardrail": {"action": "INTERVENED"}}])
    out = list(AwsBedrock(cfg(), agent_rt=rt).ask_stream(["G"], "hỏi"))
    assert out[-1]["type"] == "blocked" and not any(e["type"] == "citations" for e in out)


def test_guardrail_can_be_disabled_by_admin_config():
    rt = FakeRuntime([])
    list(AwsBedrock(cfg(), agent_rt=rt).ask_stream(["G"], "hỏi", guard=False))
    gen = rt.calls[0]["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]["generationConfiguration"]
    assert "guardrailConfiguration" not in gen


def test_throttling_is_retried(monkeypatch):
    monkeypatch.setattr("app.services.bedrock.time.sleep", lambda s: None)
    rt = FakeRuntime([{"output": {"text": "ok"}}], fail=2)
    assert list(AwsBedrock(cfg(), agent_rt=rt).ask_stream(["G"], "q"))[0]["text"] == "ok"
    assert len(rt.calls) == 3


def test_throttling_gives_up_after_three_tries(monkeypatch):
    monkeypatch.setattr("app.services.bedrock.time.sleep", lambda s: None)
    with pytest.raises(ClientError):
        list(AwsBedrock(cfg(), agent_rt=FakeRuntime(fail=5)).ask_stream(["G"], "q"))
