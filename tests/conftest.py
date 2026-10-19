import os

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql://unused:unused@127.0.0.1:1/unused"
)
os.environ["JWT_SECRET"] = "test-only-signing-secret-with-more-than-32-characters"
os.environ["CHATGROQ_API_KEY"] = "test-only"
os.environ["COHERE_API_KEY"] = "test-only"
os.environ["ENABLE_CONTENT_TRACING"] = "false"
import pytest_asyncio
from src.common.database import close_pools


@pytest_asyncio.fixture(autouse=True)
async def cleanup_pools():
    yield
    await close_pools()
