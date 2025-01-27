# tests/conftest.py
import pytest_asyncio
import logging
import json
import asyncio
from typing import Any
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)

def log_test_step(step: str, details: Any = None):
    """Helper to log test operations with consistent format."""
    msg = f"Test Step: {step}"
    if details:
        msg += f" - {details}"
    logger.info(msg)

@pytest_asyncio.fixture(scope="function")
async def mcp_client(event_loop):
    """Fixture to provide MCP client connection."""
    client = MCPClient()
    try:
        await client.connect_to_server("kg_access.py")
        yield client
    finally:
        # Run cleanup in the same event loop
        await event_loop.create_task(client.cleanup())

@pytest_asyncio.fixture(scope="function")
async def clean_db(mcp_client):
    """Fixture to ensure clean database state before and after tests."""
    async def clean():
        # Delete in correct order due to foreign key constraints
        await mcp_client.call_tool(
            "query_knowledge_graph_database",
            {"sql": "DELETE FROM properties"}
        )
        await mcp_client.call_tool(
            "query_knowledge_graph_database",
            {"sql": "DELETE FROM relationships"}
        )
        await mcp_client.call_tool(
            "query_knowledge_graph_database",
            {"sql": "DELETE FROM entities"}
        )
        
        # Verify clean state
        result = await mcp_client.call_tool(
            "query_knowledge_graph_database",
            {"sql": "SELECT COUNT(*) as count FROM entities"}
        )
        response = json.loads(result.content[0].text)
        log_test_step("Database state", f"Entity count: {response['results'][0]['count']}")
    
    await clean()  # Clean before test
    yield
    await clean()  # Clean after test