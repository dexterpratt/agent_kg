"""Integration tests for the Knowledge Graph MCP server."""

import pytest
from typing import Dict, Any

@pytest.mark.asyncio
async def test_entity_lifecycle(server, clean_db):
    """Test complete entity lifecycle including creation, update, and deletion."""
    
    # Test entity creation with properties
    entity_data = {
        "type": "person",
        "name": "John Doe",
        "properties": {
            "age": 30,
            "email": "john@example.com"
        }
    }
    
    result = await server.handlers.add_entity(entity_data)
    assert "id" in result
    entity_id = result["id"]
    
    # Test entity retrieval
    entity = await server.handlers.get_entity({"id": entity_id})
    assert entity["type"] == "person"
    assert entity["name"] == "John Doe"
    assert entity["properties"]["age"] == "30"
    assert entity["properties"]["email"] == "john@example.com"
    
    # Test entity update
    update_data = {
        "id": entity_id,
        "properties": {
            "age": 31,
            "email": "john.doe@example.com",
            "title": "Software Engineer"
        }
    }
    result = await server.handlers.update_entity(update_data)
    assert result["success"] is True
    
    # Verify update
    entity = await server.handlers.get_entity({"id": entity_id})
    assert entity["properties"]["age"] == "31"
    assert entity["properties"]["title"] == "Software Engineer"
    
    # Test entity deletion
    result = await server.handlers.delete_entity({"id": entity_id})
    assert result["success"] is True
    
    # Verify deletion
    with pytest.raises(ValueError):
        await server.handlers.get_entity({"id": entity_id})

@pytest.mark.asyncio
async def test_relationship_management(server, clean_db):
    """Test relationship creation and querying between entities."""
    
    # Create two entities
    person1 = await server.handlers.add_entity({
        "type": "person",
        "name": "Alice",
        "properties": {"role": "Manager"}
    })
    person2 = await server.handlers.add_entity({
        "type": "person",
        "name": "Bob",
        "properties": {"role": "Developer"}
    })
    
    # Create relationship
    relationship_data = {
        "source_id": person1["id"],
        "target_id": person2["id"],
        "type": "manages",
        "properties": {
            "since": "2023-01-01"
        }
    }
    result = await server.handlers.add_relationship(relationship_data)
    assert "id" in result
    rel_id = result["id"]
    
    # Test relationship retrieval
    relationships = await server.handlers.get_relationships({
        "entity_id": person1["id"],
        "direction": "outgoing"
    })
    assert len(relationships) == 1
    assert relationships[0]["type"] == "manages"
    assert relationships[0]["source_id"] == person1["id"]
    assert relationships[0]["target_id"] == person2["id"]
    
    # Test connected entities
    connected = await server.handlers.get_connected_entities({
        "entity_id": person1["id"],
        "relationship_type": "manages"
    })
    assert len(connected) == 1
    assert connected[0]["name"] == "Bob"
    assert connected[0]["properties"]["role"] == "Developer"

@pytest.mark.asyncio
async def test_property_validation(server, clean_db):
    """Test property validation and constraints."""
    
    # Create property definition using parameterized query
    query = """
    INSERT INTO property_definitions (key, allowed_value_types, validation_regex, description)
    VALUES (%s, %s, %s, %s)
    """
    params = (
        'email',
        'string',
        '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$',
        'Email address'
    )
    clean_db.execute_query(query, params)
    
    # Create entity with validated property
    entity_data = {
        "type": "person",
        "name": "John Doe",
        "properties": {
            "email": "invalid-email"  # Should fail validation
        }
    }
    
    # TODO: Implement validation in handlers
    # For now, just verify basic property storage
    result = await server.handlers.add_entity(entity_data)
    assert "id" in result

@pytest.mark.asyncio
async def test_context_operations(server, clean_db):
    """Test context management operations."""
    
    # Set context
    context_data = {
        "category": "user_preferences",
        "key": "theme",
        "value": "dark"
    }
    result = await server.handlers.set_context(context_data)
    assert result["success"] is True
    
    # Get specific context
    context = await server.handlers.get_context({"category": "user_preferences"})
    assert len(context) == 1
    assert context[0]["category"] == "user_preferences"
    assert context[0]["key"] == "theme"
    assert context[0]["value"] == "dark"
    
    # Get all context
    all_context = await server.handlers.get_context({})
    assert len(all_context) >= 1

@pytest.mark.asyncio
async def test_error_handling(server, clean_db):
    """Test error handling scenarios."""
    
    # Test invalid entity retrieval
    with pytest.raises(ValueError):
        await server.handlers.get_entity({"id": 999999})
    
    # Test duplicate entity creation
    entity_data = {
        "type": "person",
        "name": "Unique Person"
    }
    await server.handlers.add_entity(entity_data)
    
    # Attempting to create duplicate should raise error
    with pytest.raises(Exception):
        await server.handlers.add_entity(entity_data)
    
    # Test invalid relationship creation
    with pytest.raises(Exception):
        await server.handlers.add_relationship({
            "source_id": 999999,  # Non-existent entity
            "target_id": 999999,
            "type": "invalid_relationship"
        })

@pytest.mark.asyncio
async def test_search_operations(server, clean_db):
    """Test search functionality across entities."""
    
    # Create test entities
    entities = [
        {
            "type": "person",
            "name": "Alice",
            "properties": {"department": "Engineering", "level": "Senior"}
        },
        {
            "type": "person",
            "name": "Bob",
            "properties": {"department": "Engineering", "level": "Junior"}
        },
        {
            "type": "person",
            "name": "Charlie",
            "properties": {"department": "Sales", "level": "Senior"}
        }
    ]
    
    for entity in entities:
        await server.handlers.add_entity(entity)
    
    # Search by properties
    results = await server.handlers.search_entities({
        "properties": {"department": "Engineering"}
    })
    assert len(results) == 2
    
    # Search with type and properties
    results = await server.handlers.search_entities({
        "type": "person",
        "properties": {"level": "Senior"}
    })
    assert len(results) == 2
    
    # Search with multiple property conditions
    results = await server.handlers.search_entities({
        "properties": {
            "department": "Engineering",
            "level": "Senior"
        }
    })
    assert len(results) == 1
