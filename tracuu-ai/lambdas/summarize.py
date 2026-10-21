"""SQS → tạo tóm tắt bằng Claude (qua Knowledge Base, lọc theo doc_id) và lưu vào DynamoDB."""
import json

from ._common import services


def handler(event, _context):
    s = services()
    for r in event["Records"]:
        doc_id = json.loads(r["body"])["doc_id"]
        summary = s.bedrock.summarize(doc_id)
        if summary:
            s.store.update_doc(doc_id, summary=summary)
    return {"ok": True}
