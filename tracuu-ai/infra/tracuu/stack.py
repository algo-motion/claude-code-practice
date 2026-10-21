from aws_cdk import CfnOutput, Stack, Tags
from constructs import Construct

from .auth import Auth
from .data import Data
from .ingest import Ingest
from .rag import Rag
from .settings import Settings
from .web import Web


class TracuuStack(Stack):
    """Một stack duy nhất: tránh tham chiếu vòng giữa KMS key, role và tài nguyên của nhau."""

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        settings = Settings.from_node(self.node)

        data = Data(self, "Data", settings=settings)
        rag = Rag(self, "Rag", settings=settings, data=data)
        auth = Auth(self, "Auth", settings=settings)
        Ingest(self, "Ingest", settings=settings, data=data, rag=rag)
        web = Web(self, "Web", settings=settings, data=data, rag=rag, auth=auth)

        Tags.of(self).add("app", "tracuu-ai")
        CfnOutput(self, "AppUrl", value=f"https://{settings.domain_name}")
        CfnOutput(self, "AlbDnsName", value=web.alb.load_balancer_dns_name,
                  description="Nếu không dùng Route 53 tự động: trỏ CNAME của domain_name về đây")
        CfnOutput(self, "UserPoolId", value=auth.pool.user_pool_id)
        CfnOutput(self, "KnowledgeBaseId", value=rag.knowledge_base_id)
        CfnOutput(self, "DocsBucket", value=data.bucket.bucket_name)
        CfnOutput(self, "TableName", value=data.table.table_name)
