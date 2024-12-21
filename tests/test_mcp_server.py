"""Tests for MCP server functionality and tool interactions."""

import pytest
import json
from typing import Dict, Any
from mcp.types import Tool, TextContent

@pytest.mark.asyncio
async def test_list_tools(server):
    """Test that the server correctly lists available tools."""
    tools = await server.server.handle_list_tools()
    
    # Verify all required tools are present
    required_tools = {
        "add_entity",
        "get_entity",
        "update_entity",
        "delete_entity",
        "add_relationship",
        "get_relationships",
        "update_relationship",
        "delete_relationship",
        "search_entities",
        "get_connected_entities",
        "set_context",
        "get_context"
    }
    
    tool_names = {tool.name for tool in tools}
    assert required_tools.issubset(tool_names)
    
    # Verify tool schemas
    for tool in tools:
        assert isinstance(tool, Tool)
        assert tool.description
        assert tool.inputSchema.get("type") == "object"
        assert "properties" in tool.inputSchema

@pytest.mark.asyncio
async def test_tool_execution(server, clean_db):
    """Test end-to-end tool execution through the MCP server."""
    
    # Test entity creation through MCP
    entity_args = {
        "type": "person",
        "name": "Test Person",
        "properties": {
            "role": "Tester"
        }
    }
    
    result = await server.server.handle_call_tool("add_entity", entity_args)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    
    # Parse the response and verify
    response_data = json.loads(result[0].text)
    assert "id" in response_data
    entity_id = response_data["id"]
    
    # Test entity retrieval through MCP
    result = await server.server.handle_call_tool("get_entity", {"id": entity_id})
    assert len(result) == 1
    entity_data = json.loads(result[0].text)
    assert entity_data["name"] == "Test Person"
    assert entity_data["properties"]["role"] == "Tester"

@pytest.mark.asyncio
async def test_tool_error_handling(server, clean_db):
    """Test MCP server error handling for invalid tool requests."""
    
    # Test non-existent tool
    with pytest.raises(ValueError):
        await server.server.handle_call_tool("non_existent_tool", {})
    
    # Test invalid arguments
    with pytest.raises(ValueError):
        await server.server.handle_call_tool("add_entity", {})  # Missing required fields
    
    # Test invalid entity ID
    with pytest.raises(ValueError):
        await server.server.handle_call_tool("get_entity", {"id": 999999})

@pytest.mark.asyncio
async def test_complex_workflow(server, clean_db):
    """Test a complex workflow involving multiple tool calls."""
    
    # 1. Create two entities
    person1_result = await server.server.handle_call_tool("add_entity", {
        "type": "person",
        "name": "Manager",
        "properties": {"department": "Engineering"}
    })
    person1_id = json.loads(person1_result[0].text)["id"]
    
    person2_result = await server.server.handle_call_tool("add_entity", {
        "type": "person",
        "name": "Employee",
        "properties": {"skill": "Python"}
    })
    person2_id = json.loads(person2_result[0].text)["id"]
    
    # 2. Create relationship
    rel_result = await server.server.handle_call_tool("add_relationship", {
        "source_id": person1_id,
        "target_id": person2_id,
        "type": "manages",
        "properties": {"since": "2023"}
    })
    assert "id" in json.loads(rel_result[0].text)
    
    # 3. Search for entities
    search_result = await server.server.handle_call_tool("search_entities", {
        "type": "person",
        "properties": {"department": "Engineering"}
    })
    search_data = json.loads(search_result[0].text)
    assert len(search_data) == 1
    assert search_data[0]["name"] == "Manager"
    
    # 4. Get connected entities
    connected_result = await server.server.handle_call_tool("get_connected_entities", {
        "entity_id": person1_id,
        "relationship_type": "manages"
    })
    connected_data = json.loads(connected_result[0].text)
    assert len(connected_data) == 1
    assert connected_data[0]["name"] == "Employee"

@pytest.mark.asyncio
async def test_concurrent_operations(server, clean_db):
    """Test concurrent tool operations."""
    import asyncio
    
    # Create multiple entities concurrently
    async def create_entity(name: str) -> Dict[str, Any]:
        result = await server.server.handle_call_tool("add_entity", {
            "type": "person",
            "name": name,
            "properties": {"test": "concurrent"}
        })
        return json.loads(result[0].text)
    
    # Create 10 entities concurrently
    names = [f"Person{i}" for i in range(10)]
    results = await asyncio.gather(*[create_entity(name) for name in names])
    
    # Verify all entities were created
    assert len(results) == 10
    assert all("id" in result for result in results)
    
    # Search for all created entities
    search_result = await server.server.handle_call_tool("search_entities", {
        "properties": {"test": "concurrent"}
    })
    search_data = json.loads(search_result[0].text)
    assert len(search_data) == 10