"""Lớp repository. DynamoStore hiện thực mô hình single-table trong sơ đồ UML;
MemoryStore cùng giao diện, dùng cho chế độ local và test."""
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key

JOB_STATUSES = ("IN_PROGRESS", "COMPLETE", "FAILED")
HIDDEN = ("DELETED", "EXPIRED")
VN_TZ = timezone(timedelta(hours=7))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id():
    """ID sắp xếp được theo thời gian."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:6]


def _clean(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _days(n):
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _seed_job_times(j):
    """Đổi nhãn của dữ liệu mẫu ("09:41", "Hôm qua", "2 ph 14 s") thành timestamp thật để sắp xếp đúng."""
    today = datetime.now(VN_TZ).replace(second=0, microsecond=0)
    if ":" in j["started"]:
        h, m = map(int, j["started"].split(":"))
        start = today.replace(hour=h, minute=m)
    else:
        start = (today - timedelta(days=1)).replace(hour=10, minute=0)
    mins, secs = (re.search(r"(\d+) ph", j["dur"]), re.search(r"(\d+) s", j["dur"]))
    span = int(mins.group(1)) * 60 if mins else 0
    span += int(secs.group(1)) if secs else 5
    utc = timezone.utc  # mọi timestamp lưu ở UTC để so sánh chuỗi theo đúng thứ tự thời gian
    return start.astimezone(utc).isoformat(), (start + timedelta(seconds=span)).astimezone(utc).isoformat()


class MemoryStore:
    def __init__(self, seed=None):
        self.docs, self.jobs, self.sessions, self.messages = {}, {}, {}, {}
        self.queries, self.stats, self.config, self.groups = {}, {}, None, {}
        for d in (seed or {}).get("docs", []):
            self.put_doc(dict(d))
        for g in (seed or {}).get("groups", []):
            self.groups[g["name"]] = g
        for i, n in enumerate((seed or {}).get("usage", [])[-28:]):
            self.stats[("queries", _days(28)[i])] = n
        for j in (seed or {}).get("jobs", []):
            started, ended = _seed_job_times(j)
            self.jobs[j["id"]] = {"job_id": j["id"], "status": j["status"], "source": j["src"],
                                  "started_at": started, "ended_at": ended, "doc_count": j["docs"]}

    # --- documents
    def put_doc(self, doc):
        self.docs[doc["id"]] = doc

    def get_doc(self, doc_id):
        return self.docs.get(doc_id)

    def update_doc(self, doc_id, **fields):
        self.docs[doc_id].update(fields)

    def list_docs(self, groups, dept=None):
        out = [d for d in self.docs.values() if d.get("status") not in HIDDEN
               and set(d.get("groups", [])) & set(groups) and (not dept or d.get("dept") == dept)]
        return sorted(out, key=lambda d: d.get("updated_at", ""), reverse=True)

    def count_docs_by_status(self):
        out = {}
        for d in self.docs.values():
            out[d["status"]] = out.get(d["status"], 0) + 1
        return out

    # --- ingestion jobs
    def put_job(self, job):
        self.jobs[job["job_id"]] = job

    def update_job(self, job_id, **fields):
        self.jobs[job_id].update(fields)

    def list_jobs(self, status=None, limit=20):
        out = [j for j in self.jobs.values() if not status or j["status"] == status]
        return sorted(out, key=lambda j: j.get("started_at", ""), reverse=True)[:limit]

    # --- chat
    def create_session(self, user_id, title):
        s = {"id": new_id(), "user_id": user_id, "title": title[:80], "created_at": now_iso()}
        self.sessions[s["id"]] = s
        return s

    def get_session(self, user_id, session_id):
        s = self.sessions.get(session_id)
        return s if s and s["user_id"] == user_id else None

    def update_session(self, user_id, session_id, **fields):
        self.sessions[session_id].update(fields)

    def list_sessions(self, user_id, limit=30):
        out = [s for s in self.sessions.values() if s["user_id"] == user_id]
        return sorted(out, key=lambda s: s["id"], reverse=True)[:limit]

    def append_message(self, session_id, role, content, citations=None):
        m = {"message_id": new_id(), "session_id": session_id, "role": role, "content": content,
             "citations": citations or [], "created_at": now_iso()}
        self.messages.setdefault(session_id, []).append(m)
        return m

    def list_messages(self, session_id):
        return list(self.messages.get(session_id, []))

    def set_rating(self, session_id, message_id, rating):
        for m in self.messages.get(session_id, []):
            if m["message_id"] == message_id:
                m["rating"] = rating
                return True
        return False

    # --- search history
    def add_query(self, user_id, text, result_count):
        q = {"query_id": new_id(), "user_id": user_id, "text": text, "result_count": result_count,
             "created_at": now_iso()}
        self.queries[q["query_id"]] = q
        return q

    def list_queries(self, user_id, limit=50):
        out = [q for q in self.queries.values() if q["user_id"] == user_id]
        return sorted(out, key=lambda q: q["query_id"], reverse=True)[:limit]

    def delete_query(self, user_id, query_id):
        q = self.queries.get(query_id)
        if q and q["user_id"] == user_id:
            del self.queries[query_id]

    def clear_queries(self, user_id):
        for q in self.list_queries(user_id, limit=10_000):
            del self.queries[q["query_id"]]

    # --- thống kê (bộ đếm theo ngày)
    def incr_stat(self, name, n=1):
        day = datetime.now(timezone.utc).date().isoformat()
        self.stats[(name, day)] = self.stats.get((name, day), 0) + n

    def stat_series(self, name, days=28):
        return [self.stats.get((name, d), 0) for d in _days(days)]

    # --- cấu hình & nhóm
    def get_config(self):
        return self.config

    def put_config(self, cfg):
        self.config = cfg

    def list_groups(self):
        out = []
        for g in self.groups.values():
            n = sum(1 for d in self.docs.values() if g["name"] in d.get("groups", []) and d["status"] not in HIDDEN)
            out.append({**g, "docs": n})
        return out


class DynamoStore:
    """Bảng `tracuu-app`: GSI1 (nhóm → tài liệu), GSI2 (trạng thái job, danh sách nhóm)."""

    def __init__(self, table):
        self.t = table

    def _query_all(self, **kw):
        limit = kw.get("Limit")
        items, start = [], None
        while True:
            r = self.t.query(**kw, **({"ExclusiveStartKey": start} if start else {}))
            items += r["Items"]
            start = r.get("LastEvaluatedKey")
            if not start or (limit and len(items) >= limit):
                return [_clean(i) for i in items]

    @staticmethod
    def _update_expr(fields):
        return {"UpdateExpression": "SET " + ", ".join(f"#{k} = :{k}" for k in fields),
                "ExpressionAttributeNames": {f"#{k}": k for k in fields},
                "ExpressionAttributeValues": {f":{k}": v for k, v in fields.items()}}

    # --- documents
    def put_doc(self, doc):
        with self.t.batch_writer() as b:
            b.put_item(Item={"PK": f"DOC#{doc['id']}", "SK": "META", **doc})
            for g in doc.get("groups", []):
                b.put_item(Item={"PK": f"DOC#{doc['id']}", "SK": f"ACL#{g}", "doc_id": doc["id"],
                                 "GSI1PK": f"GROUP#{g}", "GSI1SK": f"DOC#{doc.get('updated_at', '')}#{doc['id']}"})

    def get_doc(self, doc_id):
        r = self.t.get_item(Key={"PK": f"DOC#{doc_id}", "SK": "META"}).get("Item")
        return _clean(r) if r else None

    def update_doc(self, doc_id, **fields):
        self.t.update_item(Key={"PK": f"DOC#{doc_id}", "SK": "META"}, **self._update_expr(fields))

    def list_docs(self, groups, dept=None):
        ids = set()
        for g in groups:
            for acl in self._query_all(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq(f"GROUP#{g}")):
                ids.add(acl["doc_id"])
        docs = [d for d in (self.get_doc(i) for i in ids) if d and d.get("status") not in HIDDEN
                and (not dept or d.get("dept") == dept)]
        return sorted(docs, key=lambda d: d.get("updated_at", ""), reverse=True)

    def count_docs_by_status(self):
        # Chỉ dùng cho trang quản trị; Scan có lọc là chấp nhận được ở tần suất thấp.
        out, start = {}, None
        while True:
            r = self.t.scan(FilterExpression="SK = :m AND begins_with(PK, :d)",
                            ExpressionAttributeValues={":m": "META", ":d": "DOC#"},
                            **({"ExclusiveStartKey": start} if start else {}))
            for i in r["Items"]:
                out[i["status"]] = out.get(i["status"], 0) + 1
            start = r.get("LastEvaluatedKey")
            if not start:
                return out

    # --- ingestion jobs
    def put_job(self, job):
        self.t.put_item(Item={"PK": f"JOB#{job['job_id']}", "SK": "META", **job,
                              "GSI2PK": f"JOBSTATUS#{job['status']}", "GSI2SK": job["started_at"]})

    def update_job(self, job_id, **fields):
        if "status" in fields:
            fields["GSI2PK"] = f"JOBSTATUS#{fields['status']}"
        self.t.update_item(Key={"PK": f"JOB#{job_id}", "SK": "META"}, **self._update_expr(fields))

    def list_jobs(self, status=None, limit=20):
        out = []
        for s in ([status] if status else JOB_STATUSES):
            out += self._query_all(IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq(f"JOBSTATUS#{s}"),
                                   ScanIndexForward=False, Limit=limit)
        return sorted(out, key=lambda j: j.get("started_at", ""), reverse=True)[:limit]

    # --- chat
    def create_session(self, user_id, title):
        s = {"id": new_id(), "user_id": user_id, "title": title[:80], "created_at": now_iso()}
        self.t.put_item(Item={"PK": f"USER#{user_id}", "SK": f"SESSION#{s['id']}", **s})
        return s

    def get_session(self, user_id, session_id):
        r = self.t.get_item(Key={"PK": f"USER#{user_id}", "SK": f"SESSION#{session_id}"}).get("Item")
        return _clean(r) if r else None

    def update_session(self, user_id, session_id, **fields):
        self.t.update_item(Key={"PK": f"USER#{user_id}", "SK": f"SESSION#{session_id}"}, **self._update_expr(fields))

    def list_sessions(self, user_id, limit=30):
        return self._query_all(KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("SESSION#"),
                               ScanIndexForward=False, Limit=limit)[:limit]

    def append_message(self, session_id, role, content, citations=None):
        m = {"message_id": new_id(), "session_id": session_id, "role": role, "content": content,
             "citations": citations or [], "created_at": now_iso()}
        self.t.put_item(Item={"PK": f"SESSION#{session_id}", "SK": f"MSG#{m['message_id']}", **m})
        return m

    def list_messages(self, session_id):
        return self._query_all(KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}") & Key("SK").begins_with("MSG#"))

    def set_rating(self, session_id, message_id, rating):
        try:
            self.t.update_item(Key={"PK": f"SESSION#{session_id}", "SK": f"MSG#{message_id}"},
                               UpdateExpression="SET rating = :r", ConditionExpression="attribute_exists(PK)",
                               ExpressionAttributeValues={":r": rating})
            return True
        except self.t.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    # --- search history (TTL 90 ngày)
    def add_query(self, user_id, text, result_count):
        q = {"query_id": new_id(), "user_id": user_id, "text": text, "result_count": result_count,
             "created_at": now_iso()}
        self.t.put_item(Item={"PK": f"USER#{user_id}", "SK": f"QUERY#{q['query_id']}",
                              "ttl": int(time.time()) + 90 * 86400, **q})
        return q

    def list_queries(self, user_id, limit=50):
        return self._query_all(KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("QUERY#"),
                               ScanIndexForward=False, Limit=limit)[:limit]

    def delete_query(self, user_id, query_id):
        self.t.delete_item(Key={"PK": f"USER#{user_id}", "SK": f"QUERY#{query_id}"})

    def clear_queries(self, user_id):
        for q in self.list_queries(user_id, limit=10_000):
            self.delete_query(user_id, q["query_id"])

    # --- thống kê
    def incr_stat(self, name, n=1):
        day = datetime.now(timezone.utc).date().isoformat()
        self.t.update_item(Key={"PK": f"STAT#{name}", "SK": f"DAY#{day}"}, UpdateExpression="ADD n :n",
                           ExpressionAttributeValues={":n": n})

    def stat_series(self, name, days=28):
        ds = _days(days)
        items = self._query_all(KeyConditionExpression=Key("PK").eq(f"STAT#{name}")
                                & Key("SK").between(f"DAY#{ds[0]}", f"DAY#{ds[-1]}"))
        by = {i["SK"][4:]: i["n"] for i in items}
        return [by.get(d, 0) for d in ds]

    # --- cấu hình & nhóm
    def get_config(self):
        r = self.t.get_item(Key={"PK": "CONFIG#kb", "SK": "META"}).get("Item")
        return json.loads(r["data"]) if r else None

    def put_config(self, cfg):
        self.t.put_item(Item={"PK": "CONFIG#kb", "SK": "META", "data": json.dumps(cfg)})

    def list_groups(self):
        groups = self._query_all(IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("GROUPS"))
        for g in groups:
            g["docs"] = self.t.query(IndexName="GSI1", Select="COUNT",
                                     KeyConditionExpression=Key("GSI1PK").eq(f"GROUP#{g['name']}"))["Count"]
        return groups
