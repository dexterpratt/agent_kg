# tests/test_property.py
import pytest
import json
import logging
from datetime import datetime
from .conftest import log_test_step

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_get_properties_entity(mcp_client, clean_db):
    """Test property retrieval for an entity."""
    log_test_step("Starting entity property retrieval test")
    
    # Create test entity with properties
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_entity",
            "properties": {
                "prop1": "value1",
                "prop2": "value2"
            }
        }
    )
    entity_id = json.loads(response.content[0].text)['id']
    
    # Get properties
    response = await mcp_client.call_tool(
        "get_properties",
        {"entity_id": entity_id}
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert len(result['properties']) == 2
    props = {p['key']: p['value'] for p in result['properties']}
    assert props['prop1'] == 'value1'
    assert props['prop2'] == 'value2'

@pytest.mark.asyncio
async def test_get_properties_relationship(mcp_client, clean_db):
    """Test property retrieval for a relationship."""
    log_test_step("Starting relationship property retrieval test")
    
    # Create test entities
    source = await mcp_client.call_tool(
        "add_entity",
        {"type": "test_type", "name": "source"}
    )
    source_id = json.loads(source.content[0].text)['id']
    
    target = await mcp_client.call_tool(
        "add_entity",
        {"type": "test_type", "name": "target"}
    )
    target_id = json.loads(target.content[0].text)['id']
    
    # Create relationship with properties
    response = await mcp_client.call_tool(
        "add_relationship",
        {
            "source_id": source_id,
            "target_id": target_id,
            "type": "test_relation",
            "properties": {
                "rel_prop1": "value1",
                "rel_prop2": "value2"
            }
        }
    )
    rel_id = json.loads(response.content[0].text)['id']
    
    # Get properties
    response = await mcp_client.call_tool(
        "get_properties",
        {"relationship_id": rel_id}
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert len(result['properties']) == 2
    props = {p['key']: p['value'] for p in result['properties']}
    assert props['rel_prop1'] == 'value1'
    assert props['rel_prop2'] == 'value2'

@pytest.mark.asyncio
async def test_update_properties_entity(mcp_client, clean_db):
    """Test property updates for an entity."""
    log_test_step("Starting entity property update test")
    
    # Create test entity
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_entity",
            "properties": {"original": "value"}
        }
    )
    entity_id = json.loads(response.content[0].text)['id']
    
    # Update properties
    update_data = {
        "entity_id": entity_id,
        "properties": {
            "original": "new_value",  # Update existing
            "new_prop": "value2"      # Add new
        }
    }
    
    response = await mcp_client.call_tool("update_properties", update_data)
    result = json.loads(response.content[0].text)
    
    assert result['success']
    
    # Verify updates
    response = await mcp_client.call_tool(
        "get_properties",
        {"entity_id": entity_id}
    )
    result = json.loads(response.content[0].text)
    props = {p['key']: p['value'] for p in result['properties']}
    
    assert props['original'] == 'new_value'
    assert props['new_prop'] == 'value2'

@pytest.mark.asyncio
async def test_delete_properties(mcp_client, clean_db):
    """Test property deletion."""
    log_test_step("Starting property deletion test")
    
    # Create test entity with properties
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_entity",
            "properties": {
                "keep": "value1",
                "delete1": "value2",
                "delete2": "value3"
            }
        }
    )
    entity_id = json.loads(response.content[0].text)['id']
    
    # Delete specific properties
    response = await mcp_client.call_tool(
        "delete_properties",
        {
            "entity_id": entity_id,
            "keys": ["delete1", "delete2"]
        }
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert len(result['deleted_properties']) == 2
    
    # Verify remaining properties
    response = await mcp_client.call_tool(
        "get_properties",
        {"entity_id": entity_id}
    )
    result = json.loads(response.content[0].text)
    
    assert len(result['properties']) == 1
    assert result['properties'][0]['key'] == 'keep'
    assert result['properties'][0]['value'] == 'value1'

@pytest.mark.asyncio
async def test_get_properties_filtered(mcp_client, clean_db):
    """Test property retrieval with key filter."""
    log_test_step("Starting filtered property retrieval test")
    
    # Create test entity with multiple properties
    response = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "test_entity",
            "properties": {
                "prop1": "value1",
                "prop2": "value2",
                "prop3": "value3"
            }
        }
    )
    entity_id = json.loads(response.content[0].text)['id']
    
    # Get specific property
    response = await mcp_client.call_tool(
        "get_properties",
        {
            "entity_id": entity_id,
            "key": "prop2"
        }
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert len(result['properties']) == 1
    assert result['properties'][0]['key'] == 'prop2'
    assert result['properties'][0]['value'] == 'value2'