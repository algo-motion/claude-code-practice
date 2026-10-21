import json
import os

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from tracuu.stack import TracuuStack

ENV = cdk.Environment(account="123456789012", region="ap-southeast-1")
CTX = {
    "domain_name": "tracuu.congty.vn",
    "certificate_arn": "arn:aws:acm:ap-southeast-1:123456789012:certificate/abc",
    "model_arn": "arn:aws:bedrock:ap-southeast-1:123456789012:inference-profile/apac.anthropic.claude-test",
}


def build(**extra):
    app = cdk.App(context={**CTX, **extra})
    return Template.from_stack(TracuuStack(app, "T", env=ENV))


@pytest.fixture(scope="module")
def t():
    return build()


def only(t, type_, prefix=""):
    found = {k: v for k, v in t.find_resources(type_).items() if k.startswith(prefix)}
    assert len(found) == 1, f"{type_} {prefix}: {list(found)}"
    return next(iter(found.values()))["Properties"]


# ---------- dữ liệu

def test_bucket_is_private_encrypted_versioned_and_emits_events(t):
    t.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True,
                                           "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
        "VersioningConfiguration": {"Status": "Enabled"},
        "BucketEncryption": {"ServerSideEncryptionConfiguration": [Match.object_like(
            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": Match.any_value()}})]},
        "CorsConfiguration": {"CorsRules": [Match.object_like(
            {"AllowedOrigins": ["https://tracuu.congty.vn"], "AllowedMethods": ["PUT", "GET"]})]},
    })
    t.has_resource_properties("Custom::S3BucketNotifications",
                              {"NotificationConfiguration": {"EventBridgeConfiguration": {}}})
    t.has_resource_properties("AWS::S3::BucketPolicy", {"PolicyDocument": {"Statement": Match.array_with([
        Match.object_like({"Effect": "Deny", "Condition": {"Bool": {"aws:SecureTransport": "false"}}})])}})


def test_table_matches_uml_single_table_design(t):
    t.has_resource_properties("AWS::DynamoDB::Table", {
        "KeySchema": [{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        "BillingMode": "PAY_PER_REQUEST",
        "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        "SSESpecification": Match.object_like({"SSEEnabled": True, "SSEType": "KMS"}),
        "DeletionProtectionEnabled": True,
        "GlobalSecondaryIndexes": Match.array_with([
            Match.object_like({"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"}}),
            Match.object_like({"IndexName": "GSI2", "Projection": {"ProjectionType": "ALL"}})]),
    })


# ---------- RAG

def test_knowledge_base_uses_s3_vectors_with_cohere_multilingual(t):
    kb = only(t, "AWS::Bedrock::KnowledgeBase")
    assert kb["StorageConfiguration"]["Type"] == "S3_VECTORS"
    assert "IndexArn" in kb["StorageConfiguration"]["S3VectorsConfiguration"]
    assert "foundation-model/cohere.embed-multilingual-v3" in json.dumps(kb["KnowledgeBaseConfiguration"])
    role = " ".join(json.dumps(p) for k, p in t.find_resources("AWS::IAM::Policy").items() if k.startswith("RagKbRole"))
    assert "cohere.embed-multilingual-v3" in role  # role của KB được phép gọi đúng model embedding


def test_vector_index_matches_embedding_dimension_and_keeps_bedrock_keys_non_filterable(t):
    idx = only(t, "AWS::S3Vectors::Index")
    assert idx["Dimension"] == 1024 and idx["DataType"] == "float32" and idx["DistanceMetric"] == "cosine"
    assert set(idx["MetadataConfiguration"]["NonFilterableMetadataKeys"]) == {"AMAZON_BEDROCK_TEXT",
                                                                             "AMAZON_BEDROCK_METADATA"}
    t.resource_count_is("AWS::S3Vectors::VectorBucket", 1)


def test_kb_role_can_use_only_its_own_index(t):
    role_policies = [p for k, p in t.find_resources("AWS::IAM::Policy").items() if k.startswith("RagKbRole")]
    stmts = [st for p in role_policies for st in p["Properties"]["PolicyDocument"]["Statement"]]
    vec = [st for st in stmts if any(a.startswith("s3vectors:") for a in st["Action"])]
    assert len(vec) == 1 and "s3vectors:QueryVectors" in vec[0]["Action"] and "s3vectors:PutVectors" in vec[0]["Action"]
    assert "*" != vec[0]["Resource"] and "VectorIndex" in json.dumps(vec[0]["Resource"])


def test_no_opensearch_resources_remain(t):
    for type_ in ("AWS::OpenSearchServerless::Collection", "AWS::OpenSearchServerless::AccessPolicy",
                  "AWS::OpenSearchServerless::SecurityPolicy"):
        t.resource_count_is(type_, 0)


def test_chunk_size_stays_under_cohere_input_limit_and_titan_override_works():
    chunk = lambda t: only(t, "AWS::Bedrock::DataSource")["VectorIngestionConfiguration"]["ChunkingConfiguration"][
        "SemanticChunkingConfiguration"]["MaxTokens"]
    assert chunk(build()) == 400  # Cohere Embed v3 nhận tối đa ~512 token
    titan = build(embedding_model_id="amazon.titan-embed-text-v2:0")
    assert chunk(titan) == 512
    assert "foundation-model/amazon.titan-embed-text-v2:0" in json.dumps(only(titan, "AWS::Bedrock::KnowledgeBase"))


def test_data_source_scoped_to_docs_prefix_with_semantic_chunking(t):
    ds = only(t, "AWS::Bedrock::DataSource")
    assert ds["DataSourceConfiguration"]["S3Configuration"]["InclusionPrefixes"] == ["docs/"]
    chunk = ds["VectorIngestionConfiguration"]["ChunkingConfiguration"]
    assert chunk["ChunkingStrategy"] == "SEMANTIC" and ds["DataDeletionPolicy"] == "RETAIN"


def test_guardrail_has_prompt_attack_filter_and_is_versioned(t):
    g = only(t, "AWS::Bedrock::Guardrail")
    types = {f["Type"]: f for f in g["ContentPolicyConfig"]["FiltersConfig"]}
    assert types["PROMPT_ATTACK"]["InputStrength"] == "HIGH" and types["PROMPT_ATTACK"]["OutputStrength"] == "NONE"
    assert g["SensitiveInformationPolicyConfig"]["RegexesConfig"][0]["Action"] == "ANONYMIZE"
    t.resource_count_is("AWS::Bedrock::GuardrailVersion", 1)


# ---------- đăng nhập & mạng

def test_cognito_requires_mfa_blocks_self_signup_and_client_has_secret(t):
    t.has_resource_properties("AWS::Cognito::UserPool", {
        "MfaConfiguration": "ON", "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
        "DeletionProtection": "ACTIVE",
        "Schema": Match.array_with([Match.object_like({"Name": "groups", "Mutable": True})])})
    t.has_resource_properties("AWS::Cognito::UserPoolClient", {
        "GenerateSecret": True, "AllowedOAuthFlows": ["code"],
        "CallbackURLs": ["https://tracuu.congty.vn/oauth2/idpresponse"],
        "SupportedIdentityProviders": ["COGNITO"]})
    t.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 0)


def test_saml_idp_is_optional_and_wired_into_the_client():
    t = build(saml_metadata_url="https://idp.congty.vn/metadata.xml")
    idp = only(t, "AWS::Cognito::UserPoolIdentityProvider")
    assert idp["ProviderType"] == "SAML" and idp["AttributeMapping"]["custom:groups"]
    t.has_resource_properties("AWS::Cognito::UserPoolClient", {"SupportedIdentityProviders": ["CompanyIdP"]})


def test_listener_authenticates_pages_denies_api_and_leaves_health_open(t):
    listeners = {l["Properties"]["Port"]: l["Properties"] for l in t.find_resources(
        "AWS::ElasticLoadBalancingV2::Listener").values()}
    https = listeners[443]
    assert https["Certificates"][0]["CertificateArn"] == CTX["certificate_arn"]
    assert [a["Type"] for a in https["DefaultActions"]] == ["authenticate-cognito", "forward"]
    assert https["DefaultActions"][0]["AuthenticateCognitoConfig"]["OnUnauthenticatedRequest"] == "authenticate"
    assert listeners[80]["DefaultActions"][0]["RedirectConfig"]["Protocol"] == "HTTPS"

    rules = {r["Properties"]["Priority"]: r["Properties"] for r in t.find_resources(
        "AWS::ElasticLoadBalancingV2::ListenerRule").values()}
    assert [a["Type"] for a in rules[1]["Actions"]] == ["forward"]  # /healthz không qua Cognito
    assert rules[1]["Conditions"][0]["PathPatternConfig"]["Values"] == ["/healthz"]
    assert rules[10]["Actions"][0]["AuthenticateCognitoConfig"]["OnUnauthenticatedRequest"] == "deny"
    assert rules[10]["Conditions"][0]["PathPatternConfig"]["Values"] == ["/api/*"]


def test_alb_hardening_and_target_health_check(t):
    attrs = {a["Key"]: a["Value"] for a in only(t, "AWS::ElasticLoadBalancingV2::LoadBalancer")["LoadBalancerAttributes"]}
    assert attrs["routing.http.drop_invalid_header_fields.enabled"] == "true"
    assert attrs["idle_timeout.timeout_seconds"] == "120"  # đủ cho luồng SSE
    assert attrs["deletion_protection.enabled"] == "true"
    t.has_resource_properties("AWS::ElasticLoadBalancingV2::TargetGroup", {
        "HealthCheckPath": "/healthz", "Port": 8000})


def test_service_config_and_prod_auth_mode(t):
    t.has_resource_properties("AWS::ECS::Service", {
        "DesiredCount": 2, "LaunchType": "FARGATE",
        "NetworkConfiguration": {"AwsvpcConfiguration": Match.object_like({"AssignPublicIp": "ENABLED"})},
        "DeploymentConfiguration": Match.object_like({"DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}})})
    env = {e["Name"]: e["Value"] for e in only(t, "AWS::ECS::TaskDefinition")["ContainerDefinitions"][0]["Environment"]}
    assert env["AUTH_MODE"] == "alb" and env["BACKEND"] == "aws"  # không bao giờ để dev auth chạy ở production
    assert env["SEARCH_TYPE"] == "SEMANTIC"  # S3 Vectors không hỗ trợ hybrid
    assert {"KB_ID", "KB_DATA_SOURCE_ID", "MODEL_ARN", "GUARDRAIL_ID", "GUARDRAIL_VERSION", "DOCS_BUCKET",
            "TABLE_NAME", "LOGOUT_URL", "GROUPS_CLAIM"} <= set(env)
    t.has_resource_properties("AWS::ECS::TaskDefinition", Match.object_like({"RuntimePlatform": {
        "CpuArchitecture": "X86_64", "OperatingSystemFamily": "LINUX"}}))


def test_no_nat_gateway_and_only_free_gateway_endpoints(t):
    t.resource_count_is("AWS::EC2::NatGateway", 0)
    t.resource_count_is("AWS::EC2::EIP", 0)
    endpoints = t.find_resources("AWS::EC2::VPCEndpoint")
    assert len(endpoints) == 2
    assert all(e["Properties"]["VpcEndpointType"] == "Gateway" for e in endpoints.values())  # interface endpoint tính phí


def test_tasks_with_public_ips_accept_traffic_only_from_the_alb(t):
    """Task có IP công khai nên security group là lớp bảo vệ duy nhất: không được mở cổng cho Internet."""
    sgs = t.find_resources("AWS::EC2::SecurityGroup")
    service_sg = next(k for k in sgs if k.startswith("WebServiceSecurityGroup"))
    assert not sgs[service_sg]["Properties"].get("SecurityGroupIngress")
    ingress = [i["Properties"] for i in t.find_resources("AWS::EC2::SecurityGroupIngress").values()]
    to_service = [i for i in ingress if service_sg in json.dumps(i.get("GroupId"))]
    assert to_service, "ALB phải được phép vào service"
    for rule in to_service:
        assert "CidrIp" not in rule and "SourceSecurityGroupId" in rule and rule["FromPort"] == 8000
    open_to_world = [k for k, v in sgs.items() for r in v["Properties"].get("SecurityGroupIngress", [])
                     if r.get("CidrIp") == "0.0.0.0/0"]
    assert set(open_to_world) <= {k for k in sgs if k.startswith("WebAlbSecurityGroup")}


def test_waf_is_attached_with_managed_rules_and_rate_limit(t):
    acl = only(t, "AWS::WAFv2::WebACL")
    names = {r["Name"] for r in acl["Rules"]}
    assert {"AWSManagedRulesCommonRuleSet", "AWSManagedRulesKnownBadInputsRuleSet", "RateLimitPerIp"} <= names
    assert "BlockOutsideCompany" not in names
    t.resource_count_is("AWS::WAFv2::WebACLAssociation", 1)


def test_waf_ip_allowlist_when_cidrs_given():
    t = build(allowed_cidrs="203.0.113.0/24, 198.51.100.7/32")
    assert only(t, "AWS::WAFv2::IPSet")["Addresses"] == ["203.0.113.0/24", "198.51.100.7/32"]
    rules = {r["Name"]: r for r in only(t, "AWS::WAFv2::WebACL")["Rules"]}
    assert rules["BlockOutsideCompany"]["Priority"] == 0 and "Block" in rules["BlockOutsideCompany"]["Action"]


# ---------- nạp tài liệu

def test_upload_events_are_batched_for_sixty_seconds(t):
    t.has_resource_properties("AWS::Events::Rule", {"EventPattern": Match.object_like({
        "source": ["aws.s3"], "detail-type": ["Object Created"],
        "detail": Match.object_like({"object": {"key": [{"prefix": "docs/"}]}})})})
    t.has_resource_properties("AWS::Lambda::EventSourceMapping", {
        "BatchSize": 100, "MaximumBatchingWindowInSeconds": 60,
        "ScalingConfig": {"MaximumConcurrency": 2}})
    t.has_resource_properties("AWS::Events::Rule", {"ScheduleExpression": "rate(1 minute)"})


def test_lambdas_use_the_handlers_in_the_repo_and_get_kb_settings(t):
    fns = {f["Properties"]["Handler"]: f["Properties"] for f in t.find_resources("AWS::Lambda::Function").values()
           if f["Properties"]["Handler"].startswith("lambdas.")}
    assert set(fns) == {"lambdas.ingest_trigger.handler", "lambdas.poll_jobs.handler", "lambdas.summarize.handler"}
    for p in fns.values():
        assert {"KB_ID", "KB_DATA_SOURCE_ID", "TABLE_NAME", "SUMMARY_QUEUE_URL"} <= set(p["Environment"]["Variables"])
        assert p["Runtime"] == "python3.12"


def test_queues_have_dead_letter_queues_and_require_tls(t):
    queues = t.find_resources("AWS::SQS::Queue")
    assert len(queues) == 4
    assert sum("RedrivePolicy" in q["Properties"] for q in queues.values()) == 2
    t.resource_count_is("AWS::SQS::QueuePolicy", 4)


def test_lambda_package_contains_only_app_and_lambdas():
    build()
    staging = os.path.join(os.path.dirname(__file__), "..", ".build", "lambda")
    assert sorted(os.listdir(staging)) == ["app", "lambdas"]
    files = [os.path.join(r, f) for r, _, fs in os.walk(staging) for f in fs]
    assert not any("__pycache__" in f or ".venv" in f for f in files)
    assert sum(os.path.getsize(f) for f in files) < 1_000_000


# ---------- an toàn & cấu hình

def test_no_wildcard_actions_and_wildcard_resources_are_the_known_exceptions(t):
    allowed_star_resource = {"bedrock:RetrieveAndGenerate", "ecr:GetAuthorizationToken"}
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            actions = [st["Action"]] if isinstance(st["Action"], str) else st["Action"]
            assert "*" not in actions, st
            resources = [st["Resource"]] if not isinstance(st["Resource"], list) else st["Resource"]
            if "*" in resources:
                assert set(actions) <= allowed_star_resource | {"s3:PutBucketNotification"}, st


def test_retain_false_makes_environment_destroyable():
    dev = build(retain="false")
    dev.has_resource_properties("AWS::DynamoDB::Table", {"DeletionProtectionEnabled": False})
    assert only(dev, "AWS::Bedrock::DataSource")["DataDeletionPolicy"] == "DELETE"
    assert next(iter(dev.find_resources("AWS::S3Vectors::Index").values()))["DeletionPolicy"] == "Delete"


def test_missing_required_context_lists_every_missing_key():
    with pytest.raises(ValueError) as e:
        TracuuStack(cdk.App(), "T", env=ENV)
    for key in ("domain_name", "certificate_arn", "model_arn"):
        assert key in str(e.value)


def test_hosted_zone_creates_alias_record_only_when_both_ids_given():
    assert build().find_resources("AWS::Route53::RecordSet") == {}
    t = build(hosted_zone_id="Z123", hosted_zone_name="congty.vn")
    assert only(t, "AWS::Route53::RecordSet")["Name"] == "tracuu.congty.vn."
