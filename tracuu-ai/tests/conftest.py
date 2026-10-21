import boto3
import pytest
from moto import mock_aws

from app import create_app
from app.config import Config
from app.services.store import DynamoStore


class TestConfig(Config):
    BACKEND = "local"
    AUTH_MODE = "dev"
    RATE_LIMIT_PER_MIN = 1000


@pytest.fixture(autouse=True)
def isolate_aws(monkeypatch):
    """Không bao giờ để test chạm vào tài khoản AWS thật của người chạy."""
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    for k, v in {"AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test", "AWS_DEFAULT_REGION": "ap-southeast-1"}.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def app():
    return create_app(TestConfig())


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def staff():
    return {"X-Dev-Role": "staff"}


@pytest.fixture
def dynamo_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
        yield ddb.create_table(
            TableName="tracuu-app", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")],
            GlobalSecondaryIndexes=[
                {"IndexName": n, "Projection": {"ProjectionType": "ALL"},
                 "KeySchema": [{"AttributeName": f"{n}PK", "KeyType": "HASH"}, {"AttributeName": f"{n}SK", "KeyType": "RANGE"}]}
                for n in ("GSI1", "GSI2")])


@pytest.fixture(params=["memory", "dynamo"])
def store(request):
    """Cùng một bộ test hợp đồng chạy trên cả hai hiện thực của Store."""
    if request.param == "memory":
        from app.services.store import MemoryStore
        yield MemoryStore()
    else:
        yield DynamoStore(request.getfixturevalue("dynamo_table"))
