from botocore.exceptions import ClientError

from ..models import doc_to_json

DEFAULT_KB_CONFIG = {"model": "Claude Sonnet", "emb": "Titan Text Embeddings V2", "chunk": "Theo ngữ nghĩa",
                     "size": 512, "overlap": 15, "topk": 6, "guard": True, "rerank": True, "pii": True}


class RagService:
    """Hỏi đáp và tìm kiếm có phân quyền. Nhóm luôn lấy từ user đã xác thực ở server."""

    def __init__(self, store, bedrock):
        self.store, self.bedrock = store, bedrock

    def kb_config(self):
        return {**DEFAULT_KB_CONFIG, **(self.store.get_config() or {})}

    def _doc_card(self, user, doc_id, text="", page=None, score=None):
        doc = self.store.get_doc(doc_id)
        if not doc or doc.get("status") in ("DELETED", "EXPIRED") or not set(doc.get("groups", [])) & set(user.groups):
            return None
        card = doc_to_json(doc)
        if text:
            card.update(passage=text, snippet=text.replace("\n", " ")[:240], page=page)
        if score is not None:
            card["score"] = round(float(score), 2)
        return card

    def _card_or_placeholder(self, user, doc_id, text, page):
        return self._doc_card(user, doc_id, text, page) or {
            "id": doc_id, "title": "Tài liệu không còn khả dụng", "type": "PDF", "dept": "—", "group": "",
            "groups": [], "passage": "", "summary": []}

    def session_messages(self, user, session_id):
        if not self.store.get_session(user.id, session_id):
            return None
        return [{"id": m["message_id"], "role": m["role"], "text": m["content"], "rating": m.get("rating"),
                 "docs": [self._card_or_placeholder(user, c["doc_id"], c.get("excerpt", ""), c.get("page"))
                          for c in m.get("citations", [])]}
                for m in self.store.list_messages(session_id)]

    def search(self, user, query):
        hits = self.bedrock.search(user.groups, query, self.kb_config()["topk"])
        best = {}
        for h in hits:  # mỗi tài liệu giữ đoạn có điểm cao nhất
            if h["doc_id"] not in best or h["score"] > best[h["doc_id"]]["score"]:
                best[h["doc_id"]] = h
        results = [c for h in sorted(best.values(), key=lambda h: -h["score"])
                   if (c := self._doc_card(user, h["doc_id"], h["text"], h["page"], h["score"]))]
        self.store.add_query(user.id, query, len(results))
        self.store.incr_stat("queries")
        return results

    def ask(self, user, question, session_id=None, save=True, doc_id=None):
        """Generator sự kiện SSE: meta, delta*, (blocked), citations, done | error.

        save=False dùng cho câu trả lời AI ở trang tìm kiếm: không tạo phiên chat, không lưu tin nhắn.
        """
        session = None
        if doc_id and not self._doc_card(user, doc_id):
            yield {"type": "error", "message": "Không tìm thấy tài liệu"}
            return
        if save:
            session = self.store.get_session(user.id, session_id) if session_id else None
            if session_id and not session:
                yield {"type": "error", "message": "Không tìm thấy phiên hội thoại"}
                return
            session = session or self.store.create_session(user.id, question)
            self.store.append_message(session["id"], "user", question)
        yield {"type": "meta", "session_id": session["id"] if session else None}

        cfg = self.kb_config()
        text, cites, blocked = "", [], False
        try:
            for ev in self.bedrock.ask_stream(user.groups, question, (session or {}).get("bedrock_session_id"),
                                              cfg["topk"], cfg["guard"], doc_id):
                if ev["type"] == "delta":
                    text += ev["text"]
                    yield ev
                elif ev["type"] == "blocked":
                    text, blocked = ev["text"], True
                    yield ev
                elif ev["type"] == "citations":
                    cites = ev["items"]
                elif ev["type"] == "session" and session and ev["id"] != session.get("bedrock_session_id"):
                    self.store.update_session(user.id, session["id"], bedrock_session_id=ev["id"])
        except ClientError as e:
            self.store.incr_stat("errors")
            yield {"type": "error", "message": "Dịch vụ đang bận, vui lòng thử lại sau",
                   "code": e.response["Error"]["Code"]}
            return

        # Giữ nguyên thứ tự để khớp mã trích dẫn [n] trong văn bản.
        docs = [self._card_or_placeholder(user, c["doc_id"], c["excerpt"], c.get("page")) for c in cites]
        msg = None
        if save:
            msg = self.store.append_message(
                session["id"], "assistant", text,
                [{"doc_id": c["doc_id"], "page": c.get("page") or 0, "excerpt": c["excerpt"][:500]} for c in cites])
            self.store.incr_stat("queries")  # truy vấn ở trang tìm kiếm đã được đếm trong search()
        if not cites and not blocked:
            self.store.incr_stat("unanswered")
        yield {"type": "citations", "docs": docs}
        yield {"type": "done", "message_id": msg["message_id"] if msg else None,
               "session_id": session["id"] if session else None}
