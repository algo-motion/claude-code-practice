from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .settings import Settings


class Data(Construct):
    """KMS, bucket tài liệu và bảng DynamoDB single-table (khoá PK/SK, GSI1, GSI2) theo sơ đồ UML."""

    def __init__(self, scope: Construct, id: str, *, settings: Settings):
        super().__init__(scope, id)
        removal = RemovalPolicy.RETAIN if settings.retain else RemovalPolicy.DESTROY

        self.key = kms.Key(self, "Key", description="Tra Cứu AI: mã hoá S3 và DynamoDB",
                           enable_key_rotation=True, removal_policy=removal)

        self.bucket = s3.Bucket(
            self, "Docs",
            encryption=s3.BucketEncryption.KMS, encryption_key=self.key, bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, versioned=True,
            event_bridge_enabled=True,  # S3 -> EventBridge -> SQS -> Lambda nạp tài liệu
            removal_policy=removal, auto_delete_objects=not settings.retain,
            lifecycle_rules=[s3.LifecycleRule(noncurrent_version_expiration=Duration.days(90),
                                              abort_incomplete_multipart_upload_after=Duration.days(7))],
            # Trình duyệt PUT thẳng lên S3 bằng presigned URL nên cần CORS cho đúng origin của ứng dụng.
            cors=[s3.CorsRule(allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.GET],
                              allowed_origins=[f"https://{settings.domain_name}"], allowed_headers=["*"],
                              exposed_headers=["ETag"], max_age=3000)])

        self.table = dynamodb.Table(
            self, "App",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED, encryption_key=self.key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True),
            time_to_live_attribute="ttl",  # lịch sử tìm kiếm tự xoá sau 90 ngày
            deletion_protection=settings.retain, removal_policy=removal)
        for name in ("GSI1", "GSI2"):
            self.table.add_global_secondary_index(
                index_name=name, projection_type=dynamodb.ProjectionType.ALL,
                partition_key=dynamodb.Attribute(name=f"{name}PK", type=dynamodb.AttributeType.STRING),
                sort_key=dynamodb.Attribute(name=f"{name}SK", type=dynamodb.AttributeType.STRING))
