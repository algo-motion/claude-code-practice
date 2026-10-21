import os


class Config:
    """Cấu hình đọc từ biến môi trường (Secrets Manager/SSM đưa vào task definition)."""

    # local: dữ liệu mẫu trong bộ nhớ, không gọi AWS. aws: DynamoDB + S3 + Bedrock.
    BACKEND = os.getenv("BACKEND", "local")
    # dev: người dùng giả lập. alb: tin header x-amzn-oidc-data do ALB ký.
    AUTH_MODE = os.getenv("AUTH_MODE", "dev")

    AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
    KB_ID = os.getenv("KB_ID", "")
    KB_DATA_SOURCE_ID = os.getenv("KB_DATA_SOURCE_ID", "")
    MODEL_ARN = os.getenv("MODEL_ARN", "")
    DOCS_BUCKET = os.getenv("DOCS_BUCKET", "")
    TABLE_NAME = os.getenv("TABLE_NAME", "tracuu-app")
    # SEMANTIC (S3 Vectors, mặc định) hoặc HYBRID (chỉ khi dùng OpenSearch làm kho vector).
    SEARCH_TYPE = os.getenv("SEARCH_TYPE", "SEMANTIC")
    GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")
    GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")

    # Claim chứa danh sách nhóm trong JWT do ALB chuyển tiếp (chuỗi cách nhau bởi dấu phẩy hoặc mảng).
    GROUPS_CLAIM = os.getenv("GROUPS_CLAIM", "custom:groups")
    ADMIN_GROUP = os.getenv("ADMIN_GROUP", "Admin")
    ALL_STAFF_GROUP = os.getenv("ALL_STAFF_GROUP", "Toàn công ty")
    # Nếu đặt, chỉ chấp nhận JWT có header signer khớp ARN của ALB.
    ALB_ARN = os.getenv("ALB_ARN", "")

    # URL đăng xuất của Cognito (hosted UI /logout?client_id=...&logout_uri=...).
    LOGOUT_URL = os.getenv("LOGOUT_URL", "/")

    RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
    MAX_QUESTION_CHARS = 2000
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    ALLOWED_EXT = {"pdf", "docx", "xlsx", "png", "jpg", "jpeg"}
    UPLOAD_URL_TTL = 15 * 60
    QUERY_TTL_DAYS = 90

    STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "dist"))
