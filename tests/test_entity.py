# tests/test_entity.py
import pytest
import json
import logging
from datetime import datetime
from .conftest import log_test_step

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_add_entity_basic(mcp_client, clean_db):
    """Test basic entity creation without properties."""
    log_test_step("Starting basic entity creation test")
    
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_name"
        }
    )
    result = json.loads(response.content[0].text)
    
    assert result['type'] == "test_type"
    assert result['name'] == "test_name"
    assert 'id' in result
    assert 'created_at' in result
    assert 'last_updated' in result

@pytest.mark.asyncio
async def test_add_entity_with_properties(mcp_client, clean_db):
    """Test entity creation with properties."""
    log_test_step("Starting entity with properties test")
    
    entity_data = {
        "type": "test_type",
        "name": "test_name",
        "properties": {
            "prop1": "value1",
            "prop2": "value2"
        }
    }
    
    response = await mcp_client.call_tool("add_entity", entity_data)
    result = json.loads(response.content[0].text)
    entity_id = result['id']
    
    # Verify entity created
    assert result['type'] == "test_type"
    assert result['name'] == "test_name"
    
    # Verify properties
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT * FROM properties WHERE entity_id = {entity_id}"}
    )
    props = json.loads(response.content[0].text)['results']
    
    assert len(props) == 2
    prop_dict = {p['key']: p['value'] for p in props}
    assert prop_dict['prop1'] == 'value1'
    assert prop_dict['prop2'] == 'value2'

@pytest.mark.asyncio
async def test_delete_entity(mcp_client, clean_db):
    """Test entity deletion."""
    log_test_step("Starting entity deletion test")
    
    # Create entity
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_name",
            "properties": {"test_prop": "test_value"}
        }
    )
    entity = json.loads(response.content[0].text)
    entity_id = entity['id']
    
    # Delete entity
    response = await mcp_client.call_tool(
        "delete_entity",
        {"id": entity_id}
    )
    result = json.loads(response.content[0].text)
    assert result['success']
    
    # Verify entity deleted
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT COUNT(*) as count FROM entities WHERE id = {entity_id}"}
    )
    result = json.loads(response.content[0].text)
    assert result['results'][0]['count'] == 0
    
    # Verify properties deleted
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT COUNT(*) as count FROM properties WHERE entity_id = {entity_id}"}
    )
    result = json.loads(response.content[0].text)
    assert result['results'][0]['count'] == 0
