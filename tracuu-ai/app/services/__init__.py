import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from .bedrock import AwsBedrock, LocalBedrock
from .documents import DocumentService
from .rag import RagService
from .storage import LocalStorage, S3Storage
from .store import DynamoStore, MemoryStore

SEED_PATH = Path(__file__).with_name("seed.json")


def build_services(cfg, store=None, bedrock=None, storage=None):
    """Lắp các service. BACKEND=local dùng dữ liệu mẫu trong bộ nhớ, BACKEND=aws dùng dịch vụ thật."""
    if cfg.BACKEND == "aws":
        import boto3
        store = store or DynamoStore(boto3.resource("dynamodb", region_name=cfg.AWS_REGION).Table(cfg.TABLE_NAME))
        bedrock = bedrock or AwsBedrock(cfg)
        storage = storage or S3Storage(cfg)
    else:
        seed = json.loads(SEED_PATH.read_text("utf-8"))
        store = store or MemoryStore(seed)
        _seed_history(store, seed)
        bedrock = bedrock or LocalBedrock(store)
        storage = storage or LocalStorage()
    return SimpleNamespace(store=store, bedrock=bedrock, storage=storage,
                           rag=RagService(store, bedrock), docs=DocumentService(cfg, store, bedrock, storage))


def _seed_history(store, seed):
    """Lịch sử tìm kiếm mẫu cho người dùng dev, rải đều ra các ngày gần đây."""
    if not isinstance(store, MemoryStore):
        return
    offsets_h = [3, 20, 28, 120, 168, 190]
    base = datetime.now(timezone.utc)
    for h, off in reversed(list(zip(seed.get("history", []), offsets_h))):
        q = store.add_query("dev-user", h["q"], h["n"])
        q["created_at"] = (base - timedelta(hours=off)).isoformat(timespec="microseconds")
