"""EventBridge Scheduler (mỗi phút) → cập nhật trạng thái job/tài liệu và đẩy yêu cầu tóm tắt vào SQS."""
import json
import os

import boto3

from app.services import pipeline

from ._common import services


def handler(_event, _context):
    sqs = boto3.client("sqs")
    queue = os.environ["SUMMARY_QUEUE_URL"]

    def enqueue(doc_id):
        sqs.send_message(QueueUrl=queue, MessageBody=json.dumps({"doc_id": doc_id}))

    s = services()
    return {"finished": pipeline.poll_jobs(s.store, s.bedrock, enqueue)}
