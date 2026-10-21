import os
import shutil

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as sources
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from .data import Data
from .rag import Rag
from .settings import Settings

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def lambda_code():
    """Chỉ đóng gói app/ và lambdas/ (Lambda runtime đã có boto3; app.services không cần Flask).

    Dựng thư mục staging sạch thay vì dùng `exclude`, vì glob của CDK không khớp thư mục bắt đầu bằng dấu chấm
    (.venv, .pytest_cache) và sẽ kéo cả virtualenv vào gói Lambda.
    """
    staging = os.path.join(PROJECT_ROOT, "infra", ".build", "lambda")
    shutil.rmtree(staging, ignore_errors=True)
    for pkg in ("app", "lambdas"):
        shutil.copytree(os.path.join(PROJECT_ROOT, pkg), os.path.join(staging, pkg),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return lambda_.Code.from_asset(staging)


class Ingest(Construct):
    """S3 → EventBridge → SQS (gom lô 60 giây) → Lambda StartIngestionJob; poll trạng thái; tóm tắt bất đồng bộ."""

    def __init__(self, scope: Construct, id: str, *, settings: Settings, data: Data, rag: Rag):
        super().__init__(scope, id)

        ingest_dlq = sqs.Queue(self, "IngestDlq", enforce_ssl=True, retention_period=Duration.days(14))
        self.ingest_queue = sqs.Queue(
            self, "IngestQueue", enforce_ssl=True, visibility_timeout=Duration.minutes(6),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=5, queue=ingest_dlq))
        summary_dlq = sqs.Queue(self, "SummaryDlq", enforce_ssl=True, retention_period=Duration.days(14))
        self.summary_queue = sqs.Queue(
            self, "SummaryQueue", enforce_ssl=True, visibility_timeout=Duration.minutes(30),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=summary_dlq))

        events.Rule(
            self, "DocUploaded", description="Tệp mới trong docs/ (bỏ qua nội dung ngoài tiền tố này)",
            event_pattern=events.EventPattern(
                source=["aws.s3"], detail_type=["Object Created"],
                detail={"bucket": {"name": [data.bucket.bucket_name]}, "object": {"key": [{"prefix": "docs/"}]}}),
            targets=[targets.SqsQueue(self.ingest_queue)])

        env = {"KB_ID": rag.knowledge_base_id, "KB_DATA_SOURCE_ID": rag.data_source_id, "MODEL_ARN": settings.model_arn, "SEARCH_TYPE": "SEMANTIC",
               "TABLE_NAME": data.table.table_name, "DOCS_BUCKET": data.bucket.bucket_name,
               "SUMMARY_QUEUE_URL": self.summary_queue.queue_url}
        code = lambda_code()

        def fn(name, handler, timeout):
            f = lambda_.Function(self, name, runtime=lambda_.Runtime.PYTHON_3_12, handler=handler, code=code,
                                 timeout=Duration.seconds(timeout), memory_size=512, environment=env)
            data.table.grant_read_write_data(f)
            return f

        ingest = fn("IngestTrigger", "lambdas.ingest_trigger.handler", 60)
        poll = fn("PollJobs", "lambdas.poll_jobs.handler", 120)
        summarize = fn("Summarize", "lambdas.summarize.handler", 300)

        kb_actions = iam.PolicyStatement(actions=["bedrock:StartIngestionJob", "bedrock:GetIngestionJob"],
                                         resources=[rag.knowledge_base_arn])
        ingest.add_to_role_policy(kb_actions)
        poll.add_to_role_policy(kb_actions)
        summarize.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:Retrieve"], resources=[rag.knowledge_base_arn]))
        summarize.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:RetrieveAndGenerate"], resources=["*"]))
        summarize.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"], resources=[settings.model_arn, "arn:aws:bedrock:*::foundation-model/*"]))
        self.summary_queue.grant_send_messages(poll)

        # Một job tại một thời điểm cho mỗi data source: concurrency 2 là mức tối thiểu SQS cho phép,
        # job trùng sẽ nhận ConflictException và được SQS giao lại ở lô sau.
        ingest.add_event_source(sources.SqsEventSource(
            self.ingest_queue, batch_size=100, max_batching_window=Duration.seconds(60), max_concurrency=2))
        summarize.add_event_source(sources.SqsEventSource(self.summary_queue, batch_size=5, max_concurrency=2))
        events.Rule(self, "PollSchedule", schedule=events.Schedule.rate(Duration.minutes(1)),
                    targets=[targets.LambdaFunction(poll)])
