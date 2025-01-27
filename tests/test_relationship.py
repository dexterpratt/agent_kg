# tests/test_relationship.py
import pytest
import json
import logging
from datetime import datetime
from .conftest import log_test_step

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_add_relationship_basic(mcp_client, clean_db):
    """Test basic relationship creation between two entities."""
    log_test_step("Starting basic relationship creation test")
    
    # Create two test entities first
    source = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "source_entity"
        }
    )
    source_id = json.loads(source.content[0].text)['id']
    
    target = await mcp_client.call_tool(
        "add_entity",
        {
            "type": "test_type",
            "name": "target_entity"
        }
    )
    target_id = json.loads(target.content[0].text)['id']
    
    # Create relationship
    response = await mcp_client.call_tool(
        "add_relationship",
        {
            "source_id": source_id,
            "target_id": target_id,
            "type": "test_relation"
        }
    )
    result = json.loads(response.content[0].text)
    
    assert result['source_id'] == source_id
    assert result['target_id'] == target_id
    assert result['type'] == "test_relation"
    assert 'id' in result
    assert 'created_at' in result
    assert 'last_updated' in result

@pytest.mark.asyncio
async def test_add_relationship_with_properties(mcp_client, clean_db):
    """Test relationship creation with properties."""
    log_test_step("Starting relationship with properties test")
    
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
    relationship_data = {
        "source_id": source_id,
        "target_id": target_id,
        "type": "test_relation",
        "properties": {
            "prop1": "value1",
            "prop2": "value2"
        }
    }
    
    response = await mcp_client.call_tool("add_relationship", relationship_data)
    result = json.loads(response.content[0].text)
    relationship_id = result['id']
    
    # Verify relationship created
    assert result['type'] == "test_relation"
    
    # Verify properties
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT * FROM properties WHERE relationship_id = {relationship_id}"}
    )
    props = json.loads(response.content[0].text)['results']
    
    assert len(props) == 2
    prop_dict = {p['key']: p['value'] for p in props}
    assert prop_dict['prop1'] == 'value1'
    assert prop_dict['prop2'] == 'value2'

@pytest.mark.asyncio
async def test_update_relationship(mcp_client, clean_db):
    """Test relationship type update."""
    log_test_step("Starting relationship update test")
    
    # Create test entities and relationship
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
    
    rel = await mcp_client.call_tool(
        "add_relationship",
        {
            "source_id": source_id,
            "target_id": target_id,
            "type": "old_type"
        }
    )
    rel_id = json.loads(rel.content[0].text)['id']
    
    # Update relationship type
    response = await mcp_client.call_tool(
        "update_relationship",
        {
            "id": rel_id,
            "type": "new_type"
        }
    )
    result = json.loads(response.content[0].text)
    
    assert result['type'] == "new_type"
    assert result['id'] == rel_id

@pytest.mark.asyncio
async def test_get_relationships_filtered(mcp_client, clean_db):
    """Test relationship retrieval with various filters."""
    log_test_step("Starting filtered relationship retrieval test")
    
    # Create test entities
    entities = []
    for i in range(3):
        response = await mcp_client.call_tool(
            "add_entity",
            {"type": "test_type", "name": f"entity_{i}"}
        )
        entities.append(json.loads(response.content[0].text)['id'])
    
    # Create multiple relationships
    relationships = [
        {"source_id": entities[0], "target_id": entities[1], "type": "type_a"},
        {"source_id": entities[1], "target_id": entities[2], "type": "type_b"},
        {"source_id": entities[0], "target_id": entities[2], "type": "type_a"}
    ]
    
    for rel in relationships:
        await mcp_client.call_tool("add_relationship", rel)
    
    # Test filtering by source
    response = await mcp_client.call_tool(
        "get_relationships",
        {"source_id": entities[0]}
    )
    result = json.loads(response.content[0].text)
    assert len(result['relationships']) == 2
    
    # Test filtering by type
    response = await mcp_client.call_tool(
        "get_relationships",
        {"type": "type_a"}
    )
    result = json.loads(response.content[0].text)
    assert len(result['relationships']) == 2
    
    # Test filtering by source and type
    response = await mcp_client.call_tool(
        "get_relationships",
        {
            "source_id": entities[0],
            "type": "type_a"
        }
    )
    result = json.loads(response.content[0].text)
    assert len(result['relationships']) == 2

@pytest.mark.asyncio
async def test_delete_relationship(mcp_client, clean_db):
    """Test relationship deletion."""
    log_test_step("Starting relationship deletion test")
    
    # Create test entities and relationship
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
    
    rel = await mcp_client.call_tool(
        "add_relationship",
        {
            "source_id": source_id,
            "target_id": target_id,
            "type": "test_type",
            "properties": {"test_prop": "test_value"}
        }
    )
    rel_id = json.loads(rel.content[0].text)['id']
    
    # Delete relationship
    response = await mcp_client.call_tool(
        "delete_relationship",
        {"id": rel_id}
    )
    result = json.loads(response.content[0].text)
    assert result['success']
    
    # Verify relationship deleted
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT COUNT(*) as count FROM relationships WHERE id = {rel_id}"}
    )
    result = json.loads(response.content[0].text)
    assert result['results'][0]['count'] == 0
    
    # Verify properties deleted
    response = await mcp_client.call_tool(
        "query_knowledge_graph_database",
        {"sql": f"SELECT COUNT(*) as count FROM properties WHERE relationship_id = {rel_id}"}
    )
    result = json.loads(response.content[0].text)
    assert result['results'][0]['count'] == 0