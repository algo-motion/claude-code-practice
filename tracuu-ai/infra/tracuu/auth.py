from aws_cdk import Aws, Duration, RemovalPolicy
from aws_cdk import aws_cognito as cognito
from constructs import Construct

from .settings import Settings

IDP_NAME = "CompanyIdP"


class Auth(Construct):
    """Cognito: ALB dùng user pool này để xác thực OIDC; nhóm người dùng đi vào claim `custom:groups`."""

    def __init__(self, scope: Construct, id: str, *, settings: Settings):
        super().__init__(scope, id)
        removal = RemovalPolicy.RETAIN if settings.retain else RemovalPolicy.DESTROY

        self.pool = cognito.UserPool(
            self, "Pool", self_sign_up_enabled=False,  # tài khoản do quản trị viên hoặc IdP cấp
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                fullname=cognito.StandardAttribute(required=False, mutable=True)),
            # Nhóm lấy từ IdP (SAML attribute mapping) nên phải ghi được; ALB chuyển nó trong x-amzn-oidc-data.
            custom_attributes={"groups": cognito.StringAttribute(mutable=True, max_len=2048)},
            mfa=cognito.Mfa.REQUIRED, mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            password_policy=cognito.PasswordPolicy(min_length=12, require_digits=True, require_lowercase=True,
                                                   require_uppercase=True, require_symbols=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            deletion_protection=settings.retain, removal_policy=removal)

        prefix = settings.cognito_prefix or f"tracuu-{Aws.ACCOUNT_ID}"
        self.domain = self.pool.add_domain("Domain", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=prefix))

        providers = []
        idp = None
        if settings.saml_metadata_url:
            idp = cognito.CfnUserPoolIdentityProvider(
                self, "Saml", user_pool_id=self.pool.user_pool_id, provider_name=IDP_NAME, provider_type="SAML",
                provider_details={"MetadataURL": settings.saml_metadata_url},
                attribute_mapping={"email": settings.saml_email_attr, "name": settings.saml_name_attr,
                                   "custom:groups": settings.saml_groups_attr})
            providers.append(cognito.UserPoolClientIdentityProvider.custom(IDP_NAME))
        else:
            providers.append(cognito.UserPoolClientIdentityProvider.COGNITO)

        attrs = (cognito.ClientAttributes().with_standard_attributes(email=True, fullname=True)
                 .with_custom_attributes("groups"))
        self.client = self.pool.add_client(
            "AlbClient", generate_secret=True,  # ALB bắt buộc client có secret
            supported_identity_providers=providers, prevent_user_existence_errors=True,
            read_attributes=attrs, write_attributes=attrs,
            access_token_validity=Duration.hours(1), id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(1),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=[f"https://{settings.domain_name}/oauth2/idpresponse"],
                logout_urls=[f"https://{settings.domain_name}/"]))
        if idp:
            self.client.node.add_dependency(idp)

        host = f"{prefix}.auth.{Aws.REGION}.amazoncognito.com"
        self.logout_url = (f"https://{host}/logout?client_id={self.client.user_pool_client_id}"
                           f"&logout_uri=https://{settings.domain_name}/")
