import pytest
from mcp import Client

from modern_mcp.bookstore import Bookstore
from modern_mcp.server import create_server


@pytest.fixture
def store():
    return Bookstore()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with Client(create_server()) as connection:
        yield connection
