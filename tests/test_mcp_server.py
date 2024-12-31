"""Tests for the MCP server implementation."""

import pytest
from src.agent_kg.server import KnowledgeGraphServer
import json

@pytest.mark.asyncio
async def test_list_tools(server):
    """Test that the server correctly lists available tools."""
    tools = await server.server.handle_list_tools()
    tool_names = [tool.name for tool in tools]
    assert "add_entity" in tool_names
    assert "update_entity" in tool_names
    assert "delete_entity" in tool_names
    assert len(tool_names) == 3  # Only these three tools should be available

@pytest.mark.asyncio
async def test_tool_execution(server):
    """Test basic entity operations through tool execution."""
    # Add entity
    add_result = await server.server.handle_call_tool("add_entity", {
        "type": "test",
        "name": "Test Entity",
        "properties": {
            "key": "value"
        }
    })
    add_response = json.loads(add_result[0].text)
    assert "id" in add_response
    entity_id = add_response["id"]

    # Update entity
    update_result = await server.server.handle_call_tool("update_entity", {
        "id": entity_id,
        "properties": {
            "key": "new_value"
        }
    })
    update_response = json.loads(update_result[0].text)
    assert update_response["success"] is True

    # Delete entity
    delete_result = await server.server.handle_call_tool("delete_entity", {
        "id": entity_id
    })
    delete_response = json.loads(delete_result[0].text)
    assert delete_response["success"] is True

@pytest.mark.asyncio
async def test_tool_error_handling(server):
    """Test error handling in tool execution."""
    # Test invalid tool name
    with pytest.raises(ValueError, match="Unknown tool"):
        await server.server.handle_call_tool("invalid_tool", {})

    # Test missing required parameters
    with pytest.raises(ValueError):
        await server.server.handle_call_tool("add_entity", {})

    # Test invalid entity ID
    with pytest.raises(ValueError):
        await server.server.handle_call_tool("update_entity", {
            "id": 999999,
            "properties": {"key": "value"}
        })
