"""Metadata phân quyền ghi cạnh mỗi tài liệu để Knowledge Base lọc khi truy xuất.

Mỗi nhóm được xem là một cờ boolean riêng (`g_<băm tên nhóm>`: true). Bộ lọc `orAll` của các phép `equals` chạy trên mọi
kho vector, còn `listContains` trên danh sách nhóm chỉ OpenSearch hỗ trợ. Tên nhóm tiếng Việt cũng không phải lo
về ký tự đặc biệt trong khoá metadata vì ta băm chúng.
"""
import hashlib


def group_key(name):
    return "g_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def metadata_attributes(doc_id, groups):
    return {"doc_id": doc_id, **{group_key(g): True for g in groups}}
