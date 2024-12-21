"""Tests for PostgreSQL database connection and query execution."""

import pytest
import psycopg2
from psycopg2.errors import OperationalError, ProgrammingError
from src.agent_kg.postgres import PostgresDB

@pytest.fixture(scope="function")
def db(test_db_config):
    """Fixture to initialize and clean up the database connection."""
    db_instance = PostgresDB(test_db_config)
    yield db_instance
    db_instance.close()

def test_connection_initialization(test_db_config):
    """Test database connection initialization with valid config."""
    db = PostgresDB(test_db_config)
    assert db.connection is not None
    assert not db.connection.closed
    db.close()

def test_invalid_connection_config():
    """Test connection initialization with invalid config."""
    with pytest.raises(ValueError, match="missing required parameters"):
        PostgresDB({})

def test_connection_retry(monkeypatch, test_db_config):
    """Test connection retry logic."""
    attempt_count = 0
    original_connect = psycopg2.connect
    
    def mock_connect(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise OperationalError("Mock connection failure")
        return original_connect(*args, **kwargs)
    
    monkeypatch.setattr(psycopg2, "connect", mock_connect)
    db = PostgresDB(test_db_config)
    assert attempt_count == 2
    assert db.connection is not None
    db.close()

def test_execute_select_query(db):
    """Test executing SELECT queries."""
    # Test simple SELECT
    result = db.execute_query("SELECT 1 as num, 'test' as str")
    assert result == [{"num": 1, "str": "test"}]
    
    # Test SELECT with parameters using %s style
    query = "SELECT %s::integer as num, %s::text as str"
    params = (42, "param")
    result = db.execute_query(query, params)
    assert result == [{"num": 42, "str": "param"}]

def test_execute_modify_query(db):
    """Test executing INSERT/UPDATE/DELETE queries using core knowledge graph tables."""
    # Test entity operations
    query = "INSERT INTO entities (type, name) VALUES (%s, %s)"
    params = ("test_type", "test_entity")
    db.execute_query(query, params)
    
    # Verify INSERT
    query = "SELECT type, name FROM entities WHERE type = %s"
    params = ("test_type",)
    result = db.execute_query(query, params)
    assert result == [{"type": "test_type", "name": "test_entity"}]
    
    # Test UPDATE
    query = "UPDATE entities SET name = %s WHERE type = %s"
    params = ("updated_entity", "test_type")
    db.execute_query(query, params)
    
    # Verify UPDATE
    query = "SELECT type, name FROM entities WHERE type = %s"
    params = ("test_type",)
    result = db.execute_query(query, params)
    assert result == [{"type": "test_type", "name": "updated_entity"}]
    
    # Test DELETE
    query = "DELETE FROM entities WHERE type = %s"
    params = ("test_type",)
    db.execute_query(query, params)
    
    # Verify DELETE
    query = "SELECT type, name FROM entities WHERE type = %s"
    params = ("test_type",)
    result = db.execute_query(query, params)
    assert result == []

def test_query_error_handling(db):
    """Test error handling for various query scenarios."""
    # Test empty query
    with pytest.raises(ValueError, match="Query cannot be empty"):
        db.execute_query("")
    
    # Test invalid SQL
    with pytest.raises(ValueError, match="Invalid query or parameters"):
        db.execute_query("INVALID SQL")
    
    # Test invalid parameters
    with pytest.raises(RuntimeError, match="Unexpected database error"):
        db.execute_query("SELECT %s", ("too", "many", "params"))

def test_connection_handling(db):
    """Test connection handling and auto-reconnection."""
    # Force connection close
    db.connection.close()
    
    # Should auto-reconnect
    result = db.execute_query("SELECT 1 as num")
    assert result == [{"num": 1}]
    assert not db.connection.closed

def test_connection_close(db):
    """Test connection closing behavior."""
    # Test normal close
    db.close()
    assert db.connection.closed
    
    # Test idempotent close
    db.close()  # Should not raise error