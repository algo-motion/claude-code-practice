from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

from .data import Data
from .settings import Settings

EMBEDDING_DIMENSIONS = 1024  # Cohere Embed Multilingual v3 cố định 1024 chiều (Titan V2 mặc định cũng 1024)
# Knowledge Base ghi nội dung đoạn và metadata hệ thống vào vector; hai khoá này không được lọc.
NON_FILTERABLE_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]


class Rag(Construct):
    """Bedrock Knowledge Base trên S3 Vectors (tính phí theo mức dùng, không có mức nền) và Guardrails.

    Đánh đổi so với OpenSearch Serverless: chỉ tìm kiếm ngữ nghĩa (không hybrid với từ khoá).
    """

    def __init__(self, scope: Construct, id: str, *, settings: Settings, data: Data):
        super().__init__(scope, id)
        stack = Stack.of(self)
        removal = RemovalPolicy.RETAIN if settings.retain else RemovalPolicy.DESTROY

        # Cohere Embed v3 nhận tối đa khoảng 512 token mỗi đoạn; chừa dư địa vì cách đếm token của hai bên khác nhau.
        chunk_tokens = 400 if settings.embedding_model_id.startswith("cohere.") else 512

        # --- Kho vector
        vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucket")
        vector_bucket.apply_removal_policy(removal)
        index = s3vectors.CfnIndex(
            self, "VectorIndex", vector_bucket_arn=vector_bucket.attr_vector_bucket_arn, data_type="float32",
            dimension=EMBEDDING_DIMENSIONS, distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=NON_FILTERABLE_KEYS))
        index.apply_removal_policy(removal)

        # --- Role cho Knowledge Base
        self.kb_role = iam.Role(
            self, "KbRole", assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": stack.account},
                            "ArnLike": {"aws:SourceArn": f"arn:{stack.partition}:bedrock:{stack.region}:{stack.account}:knowledge-base/*"}}))
        embedding_arn = f"arn:{stack.partition}:bedrock:{stack.region}::foundation-model/{settings.embedding_model_id}"
        self.kb_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_arn]))
        self.kb_role.add_to_policy(iam.PolicyStatement(
            actions=["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:PutVectors", "s3vectors:GetVectors",
                     "s3vectors:DeleteVectors"], resources=[index.attr_index_arn]))
        data.bucket.grant_read(self.kb_role)
        data.key.grant_encrypt_decrypt(self.kb_role)

        # --- Knowledge Base + data source
        kb = bedrock.CfnKnowledgeBase(
            self, "KnowledgeBase", name="tracuu-ai-kb", role_arn=self.kb_role.role_arn,
            description="Tài liệu nội bộ, lọc quyền bằng cờ metadata theo nhóm (xem app/services/acl.py)",
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_arn)),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=index.attr_index_arn)))
        kb.node.add_dependency(self.kb_role)

        source = bedrock.CfnDataSource(
            self, "DataSource", name="docs", knowledge_base_id=kb.attr_knowledge_base_id,
            data_deletion_policy="RETAIN" if settings.retain else "DELETE",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3", s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=data.bucket.bucket_arn, inclusion_prefixes=["docs/"])),
            server_side_encryption_configuration=bedrock.CfnDataSource.ServerSideEncryptionConfigurationProperty(
                kms_key_arn=data.key.key_arn),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="SEMANTIC",
                    semantic_chunking_configuration=bedrock.CfnDataSource.SemanticChunkingConfigurationProperty(
                        max_tokens=chunk_tokens, buffer_size=0, breakpoint_percentile_threshold=95))))

        self.knowledge_base_id = kb.attr_knowledge_base_id
        self.knowledge_base_arn = kb.attr_knowledge_base_arn
        self.data_source_id = source.attr_data_source_id

        # --- Guardrails: lọc nội dung, chặn prompt injection, che CCCD/thẻ/mật khẩu
        def level(t, inp="HIGH", out="HIGH"):
            return bedrock.CfnGuardrail.ContentFilterConfigProperty(type=t, input_strength=inp, output_strength=out)

        guardrail = bedrock.CfnGuardrail(
            self, "Guardrail", name="tracuu-ai-guardrail",
            description="Lọc nội dung độc hại, chặn prompt injection và che thông tin cá nhân",
            blocked_input_messaging="Xin lỗi, tôi không thể hỗ trợ nội dung này.",
            blocked_outputs_messaging="Xin lỗi, tôi không thể hiển thị câu trả lời này.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(filters_config=[
                level("HATE"), level("INSULTS"), level("SEXUAL"), level("VIOLENCE"), level("MISCONDUCT"),
                level("PROMPT_ATTACK", out="NONE")]),
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type=t, action="ANONYMIZE")
                    for t in ("CREDIT_DEBIT_CARD_NUMBER", "PASSWORD")],
                regexes_config=[bedrock.CfnGuardrail.RegexConfigProperty(
                    name="cccd", description="Số căn cước công dân 12 chữ số", pattern=r"\b\d{12}\b",
                    action="ANONYMIZE")]))
        version = bedrock.CfnGuardrailVersion(self, "GuardrailVersion",
                                              guardrail_identifier=guardrail.attr_guardrail_id)
        self.guardrail_id = guardrail.attr_guardrail_id
        self.guardrail_arn = guardrail.attr_guardrail_arn
        self.guardrail_version = version.attr_version
