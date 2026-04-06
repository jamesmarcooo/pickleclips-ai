import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app
from app.config import settings
from app.services.storage import get_r2_client
import jose.jwt as jwt
import time


def make_test_token(user_id: str = "00000000-0000-0000-0000-000000000001") -> str:
    """Create a valid Supabase-format JWT for testing."""
    payload = {
        "sub": user_id,
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def mock_db():
    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.database.close_db", new=AsyncMock()):
        yield


@pytest.fixture(autouse=True)
def clear_r2_client_cache():
    get_r2_client.cache_clear()
    yield
    get_r2_client.cache_clear()


@pytest.fixture
def test_token():
    return make_test_token()


@pytest.fixture
def test_user_id():
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
async def client(mock_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
