"""Truy xuất/sinh câu trả lời qua Bedrock Knowledge Bases.

AwsBedrock gọi dịch vụ thật. LocalBedrock có cùng giao diện nhưng chạy trên dữ liệu mẫu,
để phát triển UI và chạy test mà không cần tài khoản AWS.

ask_stream() trả về các sự kiện dạng dict:
  {"type": "delta", "text": ...}        đoạn văn bản (đã chèn mã trích dẫn dạng [n])
  {"type": "blocked", "text": ...}      Guardrails can thiệp
  {"type": "citations", "items": [...]} danh sách nguồn theo thứ tự [1], [2]...
  {"type": "session", "id": ...}        sessionId của Bedrock để nối hội thoại
"""
import json
import re
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from .acl import group_key

BLOCKED_TEXT = "Xin lỗi, tôi không thể hỗ trợ nội dung này. Bạn hãy thử đặt câu hỏi khác về tài liệu nội bộ."
NOT_FOUND_TEXT = ("Tôi không tìm thấy đoạn nào trong tài liệu bạn được xem trả lời trực tiếp câu hỏi này. "
                  "Bạn có thể diễn đạt lại cụ thể hơn.")
PROMPT_TEMPLATE = (
    "Bạn là trợ lý tra cứu tài liệu nội bộ của công ty. Chỉ trả lời dựa trên kết quả tìm kiếm dưới đây, "
    "bằng tiếng Việt, ngắn gọn, chính xác. Nếu kết quả không chứa thông tin cần thiết, hãy nói rõ là không tìm thấy.\n\n"
    "$search_results$\n\n$output_format_instructions$"
)
THROTTLE_CODES = {"ThrottlingException", "ServiceUnavailableException", "TooManyRequestsException"}


def group_filter(groups):
    """Bộ lọc metadata: chỉ truy xuất tài liệu có ít nhất một nhóm trùng với nhóm của người dùng."""
    f = [{"equals": {"key": group_key(g), "value": True}} for g in groups]
    if not f:
        return {"equals": {"key": "__no_group__", "value": True}}  # không khớp tài liệu nào
    return f[0] if len(f) == 1 else {"orAll": f}


def scoped_filter(groups, doc_id=None):
    """Lọc theo nhóm, và nếu người dùng giới hạn phạm vi vào một tài liệu thì thêm điều kiện doc_id."""
    base = group_filter(groups)
    return base if not doc_id else {"andAll": [base, {"equals": {"key": "doc_id", "value": doc_id}}]}


def doc_id_from_uri(uri):
    """s3://bucket/docs/{doc_id}/{tên tệp} -> doc_id"""
    parts = uri.split("/")
    return parts[-2] if len(parts) >= 2 else ""


def _bullets(text):
    lines = [re.sub(r"^\s*[-•*\d.)]+\s*", "", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


class AwsBedrock:
    def __init__(self, cfg, agent_rt=None, agent=None):
        self.cfg = cfg
        self.agent_rt = agent_rt or boto3.client("bedrock-agent-runtime", region_name=cfg.AWS_REGION)
        self.agent = agent or boto3.client("bedrock-agent", region_name=cfg.AWS_REGION)

    def _retry(self, fn, tries=3):
        for i in range(tries):
            try:
                return fn()
            except ClientError as e:
                if e.response["Error"]["Code"] not in THROTTLE_CODES or i == tries - 1:
                    raise
                time.sleep(0.5 * 2 ** i)

    def _vector_cfg(self, flt, top_k):
        vs = {"numberOfResults": top_k, "filter": flt}
        if self.cfg.SEARCH_TYPE in ("HYBRID", "SEMANTIC"):
            vs["overrideSearchType"] = self.cfg.SEARCH_TYPE
        return {"vectorSearchConfiguration": vs}

    def search(self, groups, query, top_k=6):
        r = self._retry(lambda: self.agent_rt.retrieve(
            knowledgeBaseId=self.cfg.KB_ID, retrievalQuery={"text": query},
            retrievalConfiguration=self._vector_cfg(group_filter(groups), top_k)))
        hits = []
        for x in r["retrievalResults"]:
            meta = x.get("metadata", {})
            uri = x.get("location", {}).get("s3Location", {}).get("uri", "")
            hits.append({"doc_id": meta.get("doc_id") or doc_id_from_uri(uri), "score": x.get("score", 0),
                         "text": x["content"].get("text", ""),
                         "page": meta.get("x-amz-bedrock-kb-document-page-number")})
        return hits

    def _kb_config(self, flt, top_k, guard):
        kb = {"knowledgeBaseId": self.cfg.KB_ID, "modelArn": self.cfg.MODEL_ARN,
              "retrievalConfiguration": self._vector_cfg(flt, top_k),
              "generationConfiguration": {"promptTemplate": {"textPromptTemplate": PROMPT_TEMPLATE}}}
        if guard and self.cfg.GUARDRAIL_ID:
            kb["generationConfiguration"]["guardrailConfiguration"] = {
                "guardrailId": self.cfg.GUARDRAIL_ID, "guardrailVersion": self.cfg.GUARDRAIL_VERSION}
        return {"type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": kb}

    def ask_stream(self, groups, question, session_id=None, top_k=6, guard=True, doc_id=None):
        params = {"input": {"text": question},
                  "retrieveAndGenerateConfiguration": self._kb_config(scoped_filter(groups, doc_id), top_k, guard)}
        if session_id:
            params["sessionId"] = session_id
        resp = self._retry(lambda: self.agent_rt.retrieve_and_generate_stream(**params))
        order, items = [], []  # thứ tự nguồn theo lần xuất hiện đầu tiên
        for ev in resp["stream"]:
            if "output" in ev:
                yield {"type": "delta", "text": ev["output"]["text"]}
            elif "guardrail" in ev and ev["guardrail"].get("action") == "INTERVENED":
                yield {"type": "blocked", "text": BLOCKED_TEXT}
                return
            elif "citation" in ev:
                marks = []
                for ref in ev["citation"].get("retrievedReferences", []):
                    uri = ref.get("location", {}).get("s3Location", {}).get("uri", "")
                    did = ref.get("metadata", {}).get("doc_id") or doc_id_from_uri(uri)
                    if did not in order:
                        order.append(did)
                        items.append({"doc_id": did, "excerpt": ref["content"].get("text", ""),
                                      "page": ref.get("metadata", {}).get("x-amz-bedrock-kb-document-page-number")})
                    n = order.index(did) + 1
                    if f"[{n}]" not in marks:
                        marks.append(f"[{n}]")
                if marks:
                    yield {"type": "delta", "text": " " + "".join(marks)}
        yield {"type": "citations", "items": items}
        if resp.get("sessionId"):
            yield {"type": "session", "id": resp["sessionId"]}

    def summarize(self, doc_id):
        flt = {"equals": {"key": "doc_id", "value": doc_id}}
        params = {"input": {"text": "Tóm tắt tài liệu này thành 3 đến 5 gạch đầu dòng ngắn bằng tiếng Việt."},
                  "retrieveAndGenerateConfiguration": self._kb_config(flt, 10, False)}
        r = self._retry(lambda: self.agent_rt.retrieve_and_generate(**params))
        return _bullets(r["output"]["text"])

    def start_ingestion(self):
        r = self.agent.start_ingestion_job(knowledgeBaseId=self.cfg.KB_ID, dataSourceId=self.cfg.KB_DATA_SOURCE_ID)
        return r["ingestionJob"]["ingestionJobId"]

    def get_ingestion_job(self, job_id):
        r = self.agent.get_ingestion_job(knowledgeBaseId=self.cfg.KB_ID, dataSourceId=self.cfg.KB_DATA_SOURCE_ID,
                                         ingestionJobId=job_id)["ingestionJob"]
        status = "IN_PROGRESS" if r["status"] in ("STARTING", "IN_PROGRESS") else r["status"]
        return {"status": status, "failure_reasons": r.get("failureReasons", [])}


class LocalBedrock:
    def __init__(self, store, seed_path=None, delay=0.02):
        self.store = store
        self.delay = delay
        self.answers = json.loads(Path(seed_path or Path(__file__).with_name("seed.json")).read_text("utf-8"))["answers"]

    def _visible(self, groups):
        return {d["id"]: d for d in self.store.list_docs(groups)}

    def search(self, groups, query, top_k=6):
        docs = self._visible(groups)
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
        scored = []
        for d in docs.values():
            blob = f"{d['title']} {d.get('passage', '')} {d.get('snippet', '')}".lower()
            hit = sum(1 for w in words if w in blob)
            scored.append((hit / max(len(words), 1), d))
        ans = next((a for a in self.answers if any(k in query.lower() for k in a["k"])), None)
        boost = {i: 1 - 0.1 * n for n, i in enumerate(ans["docs"])} if ans else {}
        scored = [(min(0.99, s * 0.5 + boost.get(d["id"], 0) * 0.5 + 0.05), d) for s, d in scored]
        scored.sort(key=lambda x: -x[0])
        return [{"doc_id": d["id"], "score": round(s, 2), "text": d.get("passage", ""), "page": 3}
                for s, d in scored[:top_k]]

    def ask_stream(self, groups, question, session_id=None, top_k=6, guard=True, doc_id=None):
        docs = self._visible(groups)
        if doc_id:  # phạm vi một tài liệu: tóm lược nội dung chính của chính tài liệu đó
            doc = docs.get(doc_id)
            text = (" ".join(doc.get("summary") or []) + " [1]") if doc and doc.get("summary") else NOT_FOUND_TEXT
            yield {"type": "delta", "text": text}
            yield {"type": "citations", "items": [{"doc_id": doc_id, "excerpt": doc.get("passage", ""), "page": 3}] if doc and doc.get("summary") else []}
            yield {"type": "session", "id": session_id or "local-session"}
            return
        ans = next((a for a in self.answers if any(k in question.lower() for k in a["k"])), None)
        if ans and not all(i in docs for i in ans["docs"]):
            ans = None  # người dùng không có quyền với mọi nguồn cần thiết
        text = ans["a"].replace("**", "") if ans else NOT_FOUND_TEXT
        chunks = re.findall(r"\S+\s*", text)
        for i in range(0, len(chunks), 3):
            time.sleep(self.delay)
            yield {"type": "delta", "text": "".join(chunks[i:i + 3])}
        items = [{"doc_id": i, "excerpt": docs[i].get("passage", ""), "page": 3 + n * 5}
                 for n, i in enumerate(ans["docs"])] if ans else []
        yield {"type": "citations", "items": items}
        yield {"type": "session", "id": session_id or "local-session"}

    def summarize(self, doc_id):
        return list((self.store.get_doc(doc_id) or {}).get("summary") or [])

    def start_ingestion(self):
        return "ing-" + str(int(time.time() * 1000))[-6:]

    def get_ingestion_job(self, job_id):
        return {"status": "COMPLETE", "failure_reasons": []}
