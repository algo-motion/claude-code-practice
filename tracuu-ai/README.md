# Tra Cứu AI

Tìm kiếm và hỏi đáp trên tài liệu nội bộ. Giao diện React (từ prototype `tracuu-ai-design`), backend Flask theo
`Kien truc AWS.html` và `Thiet ke UML.html`: Bedrock Knowledge Bases (RAG), DynamoDB single-table, S3 presigned upload,
Lambda nạp tài liệu.

## Chạy thử trên máy (không cần AWS)

```
python -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt
npm install

# terminal 1: API với dữ liệu mẫu trong bộ nhớ (BACKEND=local, AUTH_MODE=dev)
.venv\Scripts\python -m flask --app app run --port 5000
# terminal 2: giao diện (proxy /api sang :5000)
npm run dev
```

Ở chế độ local, câu trả lời và tìm kiếm là giả lập từ `app/services/seed.json`, nhưng toàn bộ luồng phân quyền,
SSE, upload (mô phỏng S3 + Lambda bằng timer), lịch sử, phản hồi và trang quản trị chạy bằng đúng code của bản AWS.
Panel "Tuỳ chỉnh" (chỉ hiện khi `npm run dev`) đổi vai trò Nhân viên/Quản trị viên qua header `X-Dev-Role`.

```
.venv\Scripts\python -m pytest        # 52 test
npm run build                         # tạo dist/, Flask tự phục vụ
```

## Cấu hình (biến môi trường)

| Biến | Ý nghĩa |
|---|---|
| `BACKEND` | `local` (mặc định) hoặc `aws` |
| `AUTH_MODE` | `dev` hoặc `alb` (tin header `x-amzn-oidc-data`). Server từ chối khởi động nếu `dev` + `aws` |
| `KB_ID`, `KB_DATA_SOURCE_ID`, `MODEL_ARN` | Knowledge Base, data source, model sinh câu trả lời |
| `SEARCH_TYPE` | `SEMANTIC` (mặc định, dùng với S3 Vectors), `HYBRID` (chỉ khi kho vector là OpenSearch), `DEFAULT` |
| `GUARDRAIL_ID`, `GUARDRAIL_VERSION` | Bedrock Guardrails (tuỳ chọn) |
| `DOCS_BUCKET`, `TABLE_NAME` | Bucket tài liệu, bảng DynamoDB (CDK tự đặt tên và truyền vào) |
| `GROUPS_CLAIM`, `ADMIN_GROUP`, `ALB_ARN`, `LOGOUT_URL` | Claim chứa nhóm, nhóm quản trị, ARN ALB để kiểm tra `signer`, URL đăng xuất Cognito |

## Hạ tầng AWS (CDK Python, thư mục `infra/`)

Một stack `Tracuu` dựng kiến trúc trong `Kien truc AWS.html`, đã bỏ các khoản tốn kém cố định: KMS + S3 + DynamoDB,
S3 Vectors + Bedrock Knowledge Base + Guardrails, Cognito, VPC (chỉ subnet public, không NAT), ECS Fargate,
ALB (HTTPS + xác thực Cognito), WAF, và chuỗi nạp tài liệu S3 → EventBridge → SQS → Lambda.

```
cd infra
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest                   # 25 test trên template CloudFormation, không cần AWS

npm install -g aws-cdk                             # CLI, cần Docker đang chạy để build image
cdk bootstrap                                      # một lần cho mỗi tài khoản/region
cdk deploy -c domain_name=tracuu.congty.vn ^
           -c certificate_arn=arn:aws:acm:ap-southeast-1:<acct>:certificate/<id> ^
           -c model_arn=<ARN model hoặc inference profile Claude đã bật trong Bedrock>
```

Context bắt buộc: `domain_name`, `certificate_arn` (ACM, cùng region), `model_arn`. Tuỳ chọn: `allowed_cidrs`
(WAF chỉ cho các dải IP này), `saml_metadata_url` (+ `saml_email_attr`, `saml_name_attr`, `saml_groups_attr`),
`hosted_zone_id` + `hosted_zone_name` (tự tạo bản ghi A), `cognito_prefix`, `desired_count`,
`retain=false` (môi trường thử, `cdk destroy` xoá cả dữ liệu), `embedding_model_id`.

Sau khi deploy:
1. Nếu không dùng `hosted_zone_*`, trỏ CNAME của `domain_name` về output `AlbDnsName`.
2. Nhóm người dùng nằm ở thuộc tính Cognito `custom:groups` (chuỗi cách nhau bởi dấu phẩy); với SAML thì được ánh xạ
   từ attribute `saml_groups_attr`. Ai có nhóm `Admin` là quản trị viên.
3. Trang Quản trị > Phân quyền đọc các item `GROUP#...` (`GSI2PK = "GROUPS"`, `GSI2SK = tên nhóm`, `members`, `src`) trong
   DynamoDB; job đồng bộ nhóm từ IdP chưa có, danh sách này trống cho đến khi bạn ghi các item đó.

**Chi phí:** không còn khoản nền lớn. S3 Vectors, DynamoDB, Lambda, SQS tính theo mức dùng. Còn lại chạy liên tục:
ALB, WAF, 2 task Fargate và địa chỉ IPv4 công khai của chúng, cộng chi phí Bedrock theo lượt gọi. Xem bảng giá AWS hiện
hành trước khi deploy.

Khác sơ đồ gốc để giảm chi phí: (1) kho vector là S3 Vectors thay cho OpenSearch Serverless, nên chỉ có tìm kiếm ngữ
nghĩa, không hybrid với từ khoá; (2) không NAT gateway và không interface endpoint (hai thứ này tính phí theo giờ và
cộng lại đắt hơn cả NAT), nên task Fargate nằm ở subnet public với IP công khai, security group chỉ cho ALB vào, và
lưu lượng tới Bedrock đi qua Internet bằng TLS; chỉ S3 và DynamoDB dùng gateway endpoint miễn phí. Nếu cần mạng
hoàn toàn riêng tư theo sơ đồ gốc, phải thêm NAT hoặc các interface endpoint và chấp nhận chi phí đó.

Chưa có so với sơ đồ: CloudFront (WAF gắn trực tiếp vào ALB), CodePipeline, X-Ray, CloudTrail và Bedrock invocation
logging (hai thứ sau là cấu hình cấp tài khoản). Biến `ALB_ARN` không được đặt vì sẽ tạo tham chiếu vòng
(ALB → service → ALB), nên Flask chưa kiểm tra trường `signer` của JWT.

## Khác với thiết kế gốc

- **Đăng nhập:** ALB xử lý OIDC với Cognito nên app không có form email/mật khẩu; màn hình đăng nhập chỉ còn nút SSO.
- **Lịch sử hội thoại:** dùng `sessionId` của Bedrock để nối ngữ cảnh thay vì tự nạp 6 lượt gần nhất.
- **Trang quản trị:** bỏ ô "Chi phí Bedrock" và "Câu hỏi chưa có câu trả lời" (không có nguồn dữ liệu); thay bằng số câu
  hỏi không tìm thấy nguồn. Cấu hình `rerank`, `chunk`, `size`, `overlap`, `pii` được lưu nhưng chưa tác động tới
  Bedrock; `topk` và `guard` có tác dụng ngay.
- **Tô sáng từ khoá** ở kết quả tìm kiếm làm ở client bằng phần tử React, không còn chèn HTML từ server.

## Chưa kiểm chứng

Code gọi Bedrock/S3/ALB được test bằng client giả và moto (DynamoDB); stack CDK mới được synth và kiểm tra bằng
assertion trên template, **chưa từng `cdk deploy` lên tài khoản AWS thật**. Lần deploy đầu có thể lộ lỗi mà test không bắt
được (giá trị thuộc tính của Bedrock/S3 Vectors, quota, model chưa bật). Cần xác nhận khi triển khai: S3 Vectors và Knowledge Base dùng được ở `ap-southeast-1`, bộ lọc `equals` trên cờ
boolean `g_<băm nhóm>` hoạt động đúng với S3 Vectors (nếu không, phân quyền theo nhóm sẽ không lọc được), tên claim nhóm trong JWT của ALB (`GROUPS_CLAIM`), model khả dụng ở `ap-southeast-1`, và định dạng
sự kiện stream của `retrieve_and_generate_stream` với phiên bản boto3 đang dùng.
