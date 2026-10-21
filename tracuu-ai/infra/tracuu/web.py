import os

from aws_cdk import Aws, Duration
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_elasticloadbalancingv2_actions as actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as r53targets
from aws_cdk import aws_wafv2 as waf
from constructs import Construct

from .auth import Auth
from .data import Data
from .rag import Rag
from .settings import Settings

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PORT = 8000


class Web(Construct):
    """VPC, Flask trên ECS Fargate, ALB (HTTPS + Cognito) và WAF."""

    def __init__(self, scope: Construct, id: str, *, settings: Settings, data: Data, rag: Rag, auth: Auth):
        super().__init__(scope, id)
        subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)

        # --- Mạng: chỉ có subnet public, không NAT gateway và không interface endpoint (cả hai đều tính phí theo
        # giờ). Task Fargate có IP công khai nhưng security group không cho vào gì ngoài ALB. Gateway endpoint của
        # S3 và DynamoDB miễn phí nên lưu lượng tới hai dịch vụ này vẫn đi trong mạng AWS.
        vpc = ec2.Vpc(self, "Vpc", max_azs=2, nat_gateways=0,
                      subnet_configuration=[ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC,
                                                                    cidr_mask=24)])
        vpc.add_gateway_endpoint("S3", service=ec2.GatewayVpcEndpointAwsService.S3, subnets=[subnets])
        vpc.add_gateway_endpoint("Dynamo", service=ec2.GatewayVpcEndpointAwsService.DYNAMODB, subnets=[subnets])

        # --- Ứng dụng
        task = ecs.FargateTaskDefinition(
            self, "Task", cpu=512, memory_limit_mib=1024,
            runtime_platform=ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.X86_64,
                                                 operating_system_family=ecs.OperatingSystemFamily.LINUX))
        task.add_container(
            "web", port_mappings=[ecs.PortMapping(container_port=PORT)], stop_timeout=Duration.seconds(60),
            image=ecs.ContainerImage.from_asset(PROJECT_ROOT, file="Dockerfile",
                                                platform=ecr_assets.Platform.LINUX_AMD64),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="web", log_retention=logs.RetentionDays.ONE_MONTH),
            environment={
                "BACKEND": "aws", "AUTH_MODE": "alb", "SEARCH_TYPE": "SEMANTIC", "AWS_REGION": Aws.REGION, "AWS_DEFAULT_REGION": Aws.REGION,
                "KB_ID": rag.knowledge_base_id, "KB_DATA_SOURCE_ID": rag.data_source_id,
                "MODEL_ARN": settings.model_arn, "GUARDRAIL_ID": rag.guardrail_id,
                "GUARDRAIL_VERSION": rag.guardrail_version, "DOCS_BUCKET": data.bucket.bucket_name,
                "TABLE_NAME": data.table.table_name, "GROUPS_CLAIM": "custom:groups", "ADMIN_GROUP": "Admin",
                "LOGOUT_URL": auth.logout_url})

        data.table.grant_read_write_data(task.task_role)
        data.bucket.grant_read_write(task.task_role)  # tạo presigned URL, ghi .metadata.json, xoá tệp
        task.task_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:Retrieve", "bedrock:StartIngestionJob", "bedrock:GetIngestionJob"],
            resources=[rag.knowledge_base_arn]))
        task.task_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:RetrieveAndGenerate"], resources=["*"]))
        task.task_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=[settings.model_arn, "arn:aws:bedrock:*::foundation-model/*"]))
        task.task_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:ApplyGuardrail"],
                                                         resources=[rag.guardrail_arn]))

        cluster = ecs.Cluster(self, "Cluster", vpc=vpc, container_insights_v2=ecs.ContainerInsights.ENABLED)
        service = ecs.FargateService(
            self, "Service", cluster=cluster, task_definition=task, desired_count=settings.desired_count,
            vpc_subnets=subnets, assign_public_ip=True, min_healthy_percent=100, max_healthy_percent=200,
            health_check_grace_period=Duration.seconds(60),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True))
        scaling = service.auto_scale_task_count(min_capacity=settings.desired_count,
                                                max_capacity=settings.desired_count * 3)
        scaling.scale_on_cpu_utilization("Cpu", target_utilization_percent=60)

        # --- ALB: /healthz không cần đăng nhập; /api/* trả 401 khi hết phiên (fetch không theo được redirect);
        # còn lại chuyển hướng người dùng sang Cognito.
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "Alb", vpc=vpc, internet_facing=True, drop_invalid_header_fields=True,
            idle_timeout=Duration.seconds(120),  # đủ cho luồng SSE
            deletion_protection=settings.retain)
        target = elbv2.ApplicationTargetGroup(
            self, "Target", vpc=vpc, port=PORT, protocol=elbv2.ApplicationProtocol.HTTP, targets=[service],
            deregistration_delay=Duration.seconds(30),
            health_check=elbv2.HealthCheck(path="/healthz", healthy_http_codes="200", interval=Duration.seconds(15)))
        forward = elbv2.ListenerAction.forward([target])

        def cognito_action(on_unauth):
            return actions.AuthenticateCognitoAction(
                user_pool=auth.pool, user_pool_client=auth.client, user_pool_domain=auth.domain, next=forward,
                session_timeout=Duration.hours(8), on_unauthenticated_request=on_unauth)

        https = self.alb.add_listener(
            "Https", port=443, ssl_policy=elbv2.SslPolicy.RECOMMENDED_TLS,
            certificates=[elbv2.ListenerCertificate.from_arn(settings.certificate_arn)],
            default_action=cognito_action(elbv2.UnauthenticatedAction.AUTHENTICATE))
        https.add_action("Health", priority=1, action=forward,
                         conditions=[elbv2.ListenerCondition.path_patterns(["/healthz"])])
        https.add_action("Api", priority=10, action=cognito_action(elbv2.UnauthenticatedAction.DENY),
                         conditions=[elbv2.ListenerCondition.path_patterns(["/api/*"])])
        self.alb.add_listener("Http", port=80, default_action=elbv2.ListenerAction.redirect(
            protocol="HTTPS", port="443", permanent=True))

        if settings.hosted_zone_id and settings.hosted_zone_name:
            zone = route53.HostedZone.from_hosted_zone_attributes(
                self, "Zone", hosted_zone_id=settings.hosted_zone_id, zone_name=settings.hosted_zone_name)
            route53.ARecord(self, "Dns", zone=zone, record_name=settings.domain_name,
                            target=route53.RecordTarget.from_alias(r53targets.LoadBalancerTarget(self.alb)))

        # --- WAF
        def vis(name):
            return waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True, metric_name=name, sampled_requests_enabled=True)

        def managed(priority, name):
            return waf.CfnWebACL.RuleProperty(
                name=name, priority=priority, override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                statement=waf.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS", name=name)),
                visibility_config=vis(name))

        rules = []
        if settings.allowed_cidrs:  # chỉ cho phép mạng công ty/VPN
            ipset = waf.CfnIPSet(self, "Allowed", scope="REGIONAL", ip_address_version="IPV4",
                                 addresses=list(settings.allowed_cidrs))
            rules.append(waf.CfnWebACL.RuleProperty(
                name="BlockOutsideCompany", priority=0, action=waf.CfnWebACL.RuleActionProperty(block={}),
                statement=waf.CfnWebACL.StatementProperty(not_statement=waf.CfnWebACL.NotStatementProperty(
                    statement=waf.CfnWebACL.StatementProperty(
                        ip_set_reference_statement=waf.CfnWebACL.IPSetReferenceStatementProperty(arn=ipset.attr_arn)))),
                visibility_config=vis("BlockOutsideCompany")))
        rules += [
            managed(1, "AWSManagedRulesCommonRuleSet"), managed(2, "AWSManagedRulesKnownBadInputsRuleSet"),
            waf.CfnWebACL.RuleProperty(
                name="RateLimitPerIp", priority=3, action=waf.CfnWebACL.RuleActionProperty(block={}),
                statement=waf.CfnWebACL.StatementProperty(rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                    limit=2000, aggregate_key_type="IP")),
                visibility_config=vis("RateLimitPerIp"))]
        acl = waf.CfnWebACL(self, "Acl", scope="REGIONAL", default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
                            rules=rules, visibility_config=vis("TracuuAcl"))
        waf.CfnWebACLAssociation(self, "AclAssoc", resource_arn=self.alb.load_balancer_arn, web_acl_arn=acl.attr_arn)
