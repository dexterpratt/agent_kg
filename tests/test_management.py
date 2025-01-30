# tests/test_management.py
import pytest
import json
import logging
from datetime import datetime
from .conftest import log_test_step

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_list_tables(mcp_client, clean_db):
    """Test listing all tables in the database."""
    log_test_step("Starting table listing test")
    
    response = await mcp_client.call_tool("list_tables", {})
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert isinstance(result['tables'], list)
    # Verify core tables exist
    core_tables = {'entities', 'relationships', 'properties'}
    assert all(table in result['tables'] for table in core_tables)

@pytest.mark.asyncio
async def test_describe_table_entities(mcp_client, clean_db):
    """Test describing the entities table schema."""
    log_test_step("Starting entities table description test")
    
    response = await mcp_client.call_tool(
        "describe_table",
        {"table_name": "entities"}
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert result['table_name'] == 'entities'
    
    # Verify expected columns exist
    columns = {col['column_name'] for col in result['columns']}
    expected_columns = {'id', 'type', 'name', 'created_at', 'last_updated'}
    assert expected_columns.issubset(columns)
    
    # Verify primary key constraint
    constraints = result['constraints']
    has_pk = any(
        c['constraint_type'] == 'PRIMARY KEY' and c['column_name'] == 'id'
        for c in constraints
    )
    assert has_pk

@pytest.mark.asyncio
async def test_describe_table_properties(mcp_client, clean_db):
    """Test describing the properties table schema."""
    log_test_step("Starting properties table description test")
    
    response = await mcp_client.call_tool(
        "describe_table",
        {"table_name": "properties"}
    )
    result = json.loads(response.content[0].text)
    
    assert result['success']
    assert result['table_name'] == 'properties'
    
    # Verify expected columns
    columns = {col['column_name'] for col in result['columns']}
    expected_columns = {
        'id', 'entity_id', 'relationship_id', 
        'key', 'value', 'value_type',
        'created_at', 'last_updated'
    }
    assert expected_columns.issubset(columns)
    
    # Verify foreign key constraints
    constraints = result['constraints']
    foreign_keys = [
        c for c in constraints 
        if c['constraint_type'] == 'FOREIGN KEY'
    ]
    assert len(foreign_keys) >= 2  # Should have FKs to entities and relationships

@pytest.mark.asyncio
async def test_describe_invalid_table(mcp_client, clean_db):
    """Test describing a non-existent table."""
    log_test_step("Starting invalid table description test")
    
    response = await mcp_client.call_tool(
        "describe_table",
        {"table_name": "nonexistent_table"}
    )
    result = json.loads(response.content[0].text)
    
    assert not result['success']
    assert 'error' in result
    assert 'does not exist' in result['error']