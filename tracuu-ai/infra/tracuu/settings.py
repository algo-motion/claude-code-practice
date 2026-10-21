from dataclasses import dataclass


def _flag(v, default):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    """Tham số triển khai, truyền bằng `cdk deploy -c khoá=giá_trị` hoặc ghi trong cdk.json (mục context)."""

    domain_name: str                 # tên miền của ứng dụng, ví dụ tracuu.congty.vn
    certificate_arn: str             # chứng chỉ ACM (cùng region với ALB) cho domain_name
    model_arn: str                   # ARN model/inference profile Claude đã bật trong Bedrock
    embedding_model_id: str = "cohere.embed-multilingual-v3"  # Titan V2 không có ở ap-southeast-1
    cognito_prefix: str = ""         # tiền tố domain Cognito; rỗng thì dùng tracuu-<account>
    hosted_zone_id: str = ""         # nếu có cả hai, tạo bản ghi A alias cho domain_name
    hosted_zone_name: str = ""
    allowed_cidrs: tuple = ()        # nếu có, WAF chặn mọi IP ngoài các dải này (VPN/mạng công ty)
    saml_metadata_url: str = ""      # nếu có, thêm IdP SAML công ty vào Cognito
    saml_email_attr: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    saml_name_attr: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
    saml_groups_attr: str = "http://schemas.xmlsoap.org/claims/Group"
    desired_count: int = 2
    retain: bool = True              # False cho môi trường thử: xoá sạch dữ liệu khi cdk destroy

    REQUIRED = ("domain_name", "certificate_arn", "model_arn")

    @classmethod
    def from_node(cls, node):
        get = node.try_get_context
        missing = [k for k in cls.REQUIRED if not get(k)]
        if missing:
            raise ValueError("Thiếu context bắt buộc: " + ", ".join(missing)
                             + ". Ví dụ: cdk deploy -c domain_name=tracuu.congty.vn -c certificate_arn=arn:aws:acm:... "
                             "-c model_arn=arn:aws:bedrock:...")
        cidrs = get("allowed_cidrs") or ""
        if isinstance(cidrs, str):
            cidrs = [c.strip() for c in cidrs.split(",") if c.strip()]
        opt = {k: get(k) for k in ("embedding_model_id", "cognito_prefix", "hosted_zone_id", "hosted_zone_name",
                                   "saml_metadata_url", "saml_email_attr", "saml_name_attr", "saml_groups_attr") if get(k)}
        return cls(domain_name=get("domain_name"), certificate_arn=get("certificate_arn"), model_arn=get("model_arn"),
                   allowed_cidrs=tuple(cidrs), desired_count=int(get("desired_count") or 2),
                   retain=_flag(get("retain"), True), **opt)
