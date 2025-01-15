"""Tests for PostgreSQL database connection and query execution."""

import pytest
import logging
from datetime import datetime
import psycopg2
from psycopg2.errors import OperationalError, ProgrammingError
from agent_kg.server import PostgresDB, Entity, Property, Relationship, ValueType

# Configure test logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s - %(filename)s:%(lineno)d'
)
logger = logging.getLogger(__name__)

def log_test_step(step, details=None):
    """Helper to log test operations with consistent format."""
    msg = f"Test Step: {step}"
    if details:
        msg += f" - {details}"
    logger.info(msg)

def get_db_state(db):
    """Get current database state for logging."""
    try:
        entities = db.execute_query("SELECT COUNT(*) as count FROM entities")
        properties = db.execute_query("SELECT COUNT(*) as count FROM properties")
        relationships = db.execute_query("SELECT COUNT(*) as count FROM relationships")
        
        return {
            'entities': entities[0]['count'] if entities else 0,
            'properties': properties[0]['count'] if properties else 0,
            'relationships': relationships[0]['count'] if relationships else 0
        }
    except Exception as e:
        logger.error(f"Failed to get database state: {e}")
        return None


@pytest.fixture(scope="function")
def db(test_db_config):
    """Fixture to initialize and clean up the database connection."""
    log_test_step("Initializing database fixture")
    db_instance = PostgresDB(test_db_config)
    
    # Log initial state
    log_test_step("Initial database state", get_db_state(db_instance))
    
    # Clean up any existing test data
    try:
        log_test_step("Cleaning up existing test data")
        db_instance.execute_query("DELETE FROM properties")
        db_instance.execute_query("DELETE FROM relationships")
        db_instance.execute_query("DELETE FROM entities")
        db_instance.connection.commit()  # Ensure cleanup is committed
        log_test_step("Initial cleanup completed")
    except Exception as e:
        logger.error(f"Error during initial cleanup: {e}")
        if db_instance.connection and not db_instance.connection.closed:
            db_instance.connection.rollback()
            logger.info("Rolled back failed cleanup")
    
    # Log state after cleanup
    log_test_step("State after initial cleanup", get_db_state(db_instance))
    
    yield db_instance
    
    # Log state before final cleanup
    log_test_step("State before final cleanup", get_db_state(db_instance))
    
    # Clean up after test
    try:
        log_test_step("Performing final cleanup")
        db_instance.execute_query("DELETE FROM properties")
        db_instance.execute_query("DELETE FROM relationships")
        db_instance.execute_query("DELETE FROM entities")
        db_instance.connection.commit()  # Ensure cleanup is committed
        log_test_step("Final cleanup completed")
    except Exception as e:
        logger.error(f"Error during final cleanup: {e}")
        if db_instance.connection and not db_instance.connection.closed:
            db_instance.connection.rollback()
            logger.info("Rolled back failed cleanup")
    finally:
        # Log final state
        log_test_step("Final database state", get_db_state(db_instance))
        db_instance.close()
        log_test_step("Database connection closed")

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

def test_entity_crud_operations(db):
    """Test entity CRUD operations."""
    log_test_step("Starting entity CRUD test")
    
    # Test add_entity
    log_test_step("Adding test entity")
    entity = db.add_entity("test_type", "test_entity")
    assert isinstance(entity, Entity)
    assert entity.type == "test_type"
    assert entity.name == "test_entity"
    assert entity.id is not None
    assert isinstance(entity.created_at, datetime)
    assert isinstance(entity.last_updated, datetime)
    log_test_step("Entity added", f"id={entity.id}")
    
    # Log state after add
    log_test_step("State after add", get_db_state(db))
    
    # Test get_entity by ID
    log_test_step("Retrieving entity by ID")
    retrieved = db.get_entity(entity_id=entity.id)
    assert retrieved is not None
    assert retrieved.id == entity.id
    assert retrieved.type == entity.type
    assert retrieved.name == entity.name
    log_test_step("Entity retrieved successfully")
    
    # Test get_entity by type and name
    log_test_step("Retrieving entity by type and name")
    retrieved = db.get_entity(type="test_type", name="test_entity")
    assert retrieved is not None
    assert retrieved.id == entity.id
    log_test_step("Entity retrieved successfully")
    
    # Test update_entity
    log_test_step("Updating entity")
    updated = db.update_entity(entity.id, name="updated_entity")
    assert updated is not None
    assert updated.id == entity.id
    assert updated.name == "updated_entity"
    assert updated.type == "test_type"
    assert updated.last_updated > entity.last_updated
    log_test_step("Entity updated successfully")
    
    # Log state after update
    log_test_step("State after update", get_db_state(db))
    
    # Test delete_entity
    log_test_step("Deleting entity")
    assert db.delete_entity(entity.id) is True
    assert db.get_entity(entity_id=entity.id) is None
    log_test_step("Entity deleted successfully")
    
    # Log final state
    log_test_step("Final state", get_db_state(db))

def test_entity_validation(db):
    """Test entity operation validation."""
    # Test empty type/name validation
    with pytest.raises(ValueError, match="Entity type cannot be empty"):
        db.add_entity("", "test")
    with pytest.raises(ValueError, match="Entity name cannot be empty"):
        db.add_entity("test", "")
    
    # Test invalid get_entity params
    with pytest.raises(ValueError, match="Must provide either entity_id or both type and name"):
        db.get_entity()
    with pytest.raises(ValueError, match="Must provide either entity_id or both type and name"):
        db.get_entity(type="test")
    
    # Test invalid update params
    with pytest.raises(ValueError, match="Entity ID is required"):
        db.update_entity(None)
    with pytest.raises(ValueError, match="At least one of type or name must be provided"):
        db.update_entity(1)
    with pytest.raises(ValueError, match="Entity type cannot be empty"):
        db.update_entity(1, type="")
    
    # Test invalid delete params
    with pytest.raises(ValueError, match="Entity ID is required"):
        db.delete_entity(None)

def test_query_error_handling(db):
    """Test error handling for various query scenarios."""
    # Test empty query
    with pytest.raises(ValueError, match="Query cannot be empty"):
        db.execute_query("")
    
    # Test syntax error
    with pytest.raises(ValueError, match="Query error"):
        db.execute_query("SELECT * FROM users WHERE;")  # Invalid SQL syntax
    
    # Test invalid table
    with pytest.raises(ValueError, match="Query error"):
        db.execute_query("SELECT * FROM nonexistent_table")
    
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

@pytest.fixture
def test_entity(db):
    """Fixture to create a test entity."""
    entity = db.add_entity("test_type", "test_entity")
    yield entity
    try:
        db.delete_entity(entity.id)
    except:
        pass

def test_property_crud_operations(db, test_entity, test_entities):
    """Test property CRUD operations for both entities and relationships."""
    # Get test entities for relationship
    entity1, entity2 = test_entities
    
    # Create a test relationship
    relationship = db.add_relationship(entity1.id, entity2.id, "test_relation")
    # Test add_property for entity
    entity_prop = db.add_property(
        key="entity_key",
        value="entity_value",
        value_type=ValueType.STRING,
        entity_id=test_entity.id
    )
    
    # Test add_property for relationship
    rel_prop = db.add_property(
        key="rel_key",
        value="rel_value",
        value_type=ValueType.STRING,
        relationship_id=relationship.id
    )
    # Verify entity property
    assert isinstance(entity_prop, Property)
    assert entity_prop.key == "entity_key"
    assert entity_prop.value == "entity_value"
    assert entity_prop.value_type == ValueType.STRING
    assert entity_prop.entity_id == test_entity.id
    assert entity_prop.relationship_id is None
    assert entity_prop.id is not None
    assert isinstance(entity_prop.created_at, datetime)
    assert isinstance(entity_prop.last_updated, datetime)
    
    # Verify relationship property
    assert isinstance(rel_prop, Property)
    assert rel_prop.key == "rel_key"
    assert rel_prop.value == "rel_value"
    assert rel_prop.value_type == ValueType.STRING
    assert rel_prop.relationship_id == relationship.id
    assert rel_prop.entity_id is None
    assert rel_prop.id is not None
    assert isinstance(rel_prop.created_at, datetime)
    assert isinstance(rel_prop.last_updated, datetime)
    
    # Test get_properties for entity
    props = db.get_properties(entity_id=test_entity.id)
    assert len(props) == 1
    assert props[0].id == entity_prop.id
    
    # Test get_properties for relationship
    props = db.get_properties(relationship_id=relationship.id)
    assert len(props) == 1
    assert props[0].id == rel_prop.id
    
    # Test get_properties with key filter for entity
    props = db.get_properties(entity_id=test_entity.id, key="entity_key")
    assert len(props) == 1
    assert props[0].id == entity_prop.id
    
    # Test get_properties with key filter for relationship
    props = db.get_properties(relationship_id=relationship.id, key="rel_key")
    assert len(props) == 1
    assert props[0].id == rel_prop.id
    
    # Test get_properties with non-existent keys
    props = db.get_properties(entity_id=test_entity.id, key="non_existent")
    assert len(props) == 0
    props = db.get_properties(relationship_id=relationship.id, key="non_existent")
    assert len(props) == 0
    
    # Test update_property for entity
    updated_entity_prop = db.update_property(
        entity_prop.id,
        value="updated_entity_value",
        value_type=ValueType.STRING
    )
    assert updated_entity_prop is not None
    assert updated_entity_prop.id == entity_prop.id
    assert updated_entity_prop.value == "updated_entity_value"
    assert updated_entity_prop.last_updated > entity_prop.last_updated
    
    # Test update_property for relationship
    updated_rel_prop = db.update_property(
        rel_prop.id,
        value="updated_rel_value",
        value_type=ValueType.STRING
    )
    assert updated_rel_prop is not None
    assert updated_rel_prop.id == rel_prop.id
    assert updated_rel_prop.value == "updated_rel_value"
    assert updated_rel_prop.last_updated > rel_prop.last_updated
    
    # Test delete_property for entity
    assert db.delete_property(entity_prop.id) is True
    props = db.get_properties(entity_id=test_entity.id)
    assert len(props) == 0
    
    # Test delete_property for relationship
    assert db.delete_property(rel_prop.id) is True
    props = db.get_properties(relationship_id=relationship.id)
    assert len(props) == 0

def test_property_value_types(db, test_entity):
    """Test different property value types."""
    # Test string value
    str_prop = db.add_property(
        key="str_key",
        value="test",
        value_type="STRING",
        entity_id=test_entity.id
    )
    assert str_prop.value_type == ValueType.STRING
    
    # Test number value
    num_prop = db.add_property(
        key="num_key",
        value="42",
        value_type=ValueType.NUMBER,
        entity_id=test_entity.id
    )
    assert num_prop.value_type == ValueType.NUMBER
    
    # Test boolean value
    bool_prop = db.add_property(
        key="bool_key",
        value="true",
        value_type="BOOLEAN",
        entity_id=test_entity.id
    )
    assert bool_prop.value_type == ValueType.BOOLEAN
    
    # Test datetime value
    dt_prop = db.add_property(
        key="dt_key",
        value="2024-01-01T00:00:00",
        value_type=ValueType.DATETIME,
        entity_id=test_entity.id
    )
    assert dt_prop.value_type == ValueType.DATETIME
    
    # Test JSON value
    json_prop = db.add_property(
        key="json_key",
        value='{"key": "value"}',
        value_type="JSON",
        entity_id=test_entity.id
    )
    assert json_prop.value_type == ValueType.JSON

def test_property_validation(db, test_entity, test_entities):
    """Test property operation validation for both entities and relationships."""
    # Get test entities for relationship
    entity1, entity2 = test_entities
    relationship = db.add_relationship(entity1.id, entity2.id, "test_relation")
    # Test empty key validation for both entity and relationship
    with pytest.raises(ValueError, match="Property key cannot be empty"):
        db.add_property("", "test", ValueType.STRING, entity_id=test_entity.id)
    with pytest.raises(ValueError, match="Property key cannot be empty"):
        db.add_property("", "test", ValueType.STRING, relationship_id=relationship.id)
    
    # Test None value validation for both
    with pytest.raises(ValueError, match="Property value cannot be None"):
        db.add_property("key", None, ValueType.STRING, entity_id=test_entity.id)
    with pytest.raises(ValueError, match="Property value cannot be None"):
        db.add_property("key", None, ValueType.STRING, relationship_id=relationship.id)
    
    # Test missing entity/relationship validation
    with pytest.raises(ValueError, match="Must provide either entity_id or relationship_id"):
        db.add_property("key", "value", ValueType.STRING)
    
    # Test both entity and relationship validation
    with pytest.raises(ValueError, match="Cannot provide both entity_id and relationship_id"):
        db.add_property("key", "value", ValueType.STRING, entity_id=test_entity.id, relationship_id=relationship.id)
    
    # Test invalid value type validation for both
    with pytest.raises(ValueError, match="Invalid value_type"):
        db.add_property("key", "value", "INVALID", entity_id=test_entity.id)
    with pytest.raises(ValueError, match="Invalid value_type"):
        db.add_property("key", "value", "INVALID", relationship_id=relationship.id)
    
    # Test get_properties validation
    with pytest.raises(ValueError, match="Must provide either entity_id or relationship_id"):
        db.get_properties()
    with pytest.raises(ValueError, match="Cannot provide both entity_id and relationship_id"):
        db.get_properties(entity_id=test_entity.id, relationship_id=relationship.id)
    
    # Test update_property validation
    with pytest.raises(ValueError, match="Property ID is required"):
        db.update_property(None, "value")
    with pytest.raises(ValueError, match="Must provide either value or value_type"):
        db.update_property(1)
    
    # Test delete_property validation
    with pytest.raises(ValueError, match="Property ID is required"):
        db.delete_property(None)

@pytest.fixture
def test_entities(db):
    """Fixture to create test entities for relationship tests."""
    entity1 = db.add_entity("test_type_1", "test_entity_1")
    entity2 = db.add_entity("test_type_2", "test_entity_2")
    yield entity1, entity2
    try:
        db.delete_entity(entity1.id)
        db.delete_entity(entity2.id)
    except:
        pass

def test_relationship_crud_operations(db, test_entities):
    """Test relationship CRUD operations."""
    entity1, entity2 = test_entities
    
    # Test add_relationship
    rel = db.add_relationship(
        source_id=entity1.id,
        target_id=entity2.id,
        type="test_relation"
    )
    assert isinstance(rel, Relationship)
    assert rel.source_id == entity1.id
    assert rel.target_id == entity2.id
    assert rel.type == "test_relation"
    assert rel.id is not None
    assert isinstance(rel.created_at, datetime)
    assert isinstance(rel.last_updated, datetime)
    
    # Test get_relationships
    rels = db.get_relationships(source_id=entity1.id)
    assert len(rels) == 1
    assert rels[0].id == rel.id
    
    # Test get_relationships with type filter
    rels = db.get_relationships(type="test_relation")
    assert len(rels) == 1
    assert rels[0].id == rel.id
    
    # Test get_relationships with non-existent type
    rels = db.get_relationships(type="non_existent")
    assert len(rels) == 0
    
    # Test update_relationship
    updated = db.update_relationship(rel.id, type="updated_relation")
    assert updated is not None
    assert updated.id == rel.id
    assert updated.type == "updated_relation"
    assert updated.last_updated > rel.last_updated
    
    # Test delete_relationship
    assert db.delete_relationship(rel.id) is True
    rels = db.get_relationships(source_id=entity1.id)
    assert len(rels) == 0

def test_get_entity_relationships(db, test_entities):
    """Test getting relationships for an entity."""
    entity1, entity2 = test_entities
    
    # Create relationships in both directions
    outgoing = db.add_relationship(
        source_id=entity1.id,
        target_id=entity2.id,
        type="outgoing_relation"
    )
    incoming = db.add_relationship(
        source_id=entity2.id,
        target_id=entity1.id,
        type="incoming_relation"
    )
    
    # Test get_entity_relationships with both directions
    rels = db.get_entity_relationships(entity1.id)
    assert len(rels) == 2
    
    # Verify relationship tuples contain correct data
    for rel, source, target in rels:
        if rel.id == outgoing.id:
            assert source.id == entity1.id
            assert target.id == entity2.id
        else:
            assert source.id == entity2.id
            assert target.id == entity1.id
    
    # Test outgoing only
    rels = db.get_entity_relationships(
        entity1.id,
        include_incoming=False,
        include_outgoing=True
    )
    assert len(rels) == 1
    rel, source, target = rels[0]
    assert rel.id == outgoing.id
    assert source.id == entity1.id
    assert target.id == entity2.id
    
    # Test incoming only
    rels = db.get_entity_relationships(
        entity1.id,
        include_incoming=True,
        include_outgoing=False
    )
    assert len(rels) == 1
    rel, source, target = rels[0]
    assert rel.id == incoming.id
    assert source.id == entity2.id
    assert target.id == entity1.id
    
    # Test with type filter
    rels = db.get_entity_relationships(
        entity1.id,
        type="outgoing_relation"
    )
    assert len(rels) == 1
    rel, source, target = rels[0]
    assert rel.id == outgoing.id

def test_relationship_validation(db, test_entities):
    """Test relationship operation validation."""
    entity1, entity2 = test_entities
    
    # Test empty type validation
    with pytest.raises(ValueError, match="Relationship type cannot be empty"):
        db.add_relationship(entity1.id, entity2.id, "")
    
    # Test missing source/target validation
    with pytest.raises(ValueError, match="Source entity ID is required"):
        db.add_relationship(None, entity2.id, "test")
    with pytest.raises(ValueError, match="Target entity ID is required"):
        db.add_relationship(entity1.id, None, "test")
    
    # Test update validation
    with pytest.raises(ValueError, match="Relationship ID is required"):
        db.update_relationship(None, "test")
    with pytest.raises(ValueError, match="Relationship type cannot be empty"):
        db.update_relationship(1, "")
    
    # Test delete validation
    with pytest.raises(ValueError, match="Relationship ID is required"):
        db.delete_relationship(None)
    
    # Test get_entity_relationships validation
    with pytest.raises(ValueError, match="Entity ID is required"):
        db.get_entity_relationships(None)
    with pytest.raises(ValueError, match="Must include at least one relationship direction"):
        db.get_entity_relationships(1, include_incoming=False, include_outgoing=False)

def test_read_only_query_validation(db):
    """Test validation of read-only queries."""
    # Valid SELECT queries
    assert db.is_read_only_query("SELECT * FROM entities")
    assert db.is_read_only_query("""
        -- Comment
        SELECT id, name 
        FROM entities 
        WHERE type = 'test'
    """)
    assert db.is_read_only_query("SELECT COUNT(*) FROM properties")
    
    # Invalid queries (write operations)
    assert not db.is_read_only_query("INSERT INTO entities (type, name) VALUES ('test', 'test')")
    assert not db.is_read_only_query("UPDATE entities SET name = 'new' WHERE id = 1")
    assert not db.is_read_only_query("DELETE FROM entities WHERE id = 1")
    assert not db.is_read_only_query("DROP TABLE entities")
    assert not db.is_read_only_query("CREATE TABLE test (id int)")
    assert not db.is_read_only_query("ALTER TABLE entities ADD COLUMN test text")
    assert not db.is_read_only_query("TRUNCATE TABLE entities")

def test_read_only_query_enforcement(db):
    """Test enforcement of read-only queries."""
    # Test valid SELECT query
    result = db.execute_query("SELECT 1 as num", enforce_read_only=True)
    assert result == [{"num": 1}]
    
    # Test write operations with enforcement
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        db.execute_query("INSERT INTO entities (type, name) VALUES ('test', 'test')", enforce_read_only=True)
    
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        db.execute_query("UPDATE entities SET name = 'new' WHERE id = 1", enforce_read_only=True)
    
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        db.execute_query("DELETE FROM entities WHERE id = 1", enforce_read_only=True)

def test_data_persistence_after_failed_query(db):
    """Test that data persists after failed queries."""
    # Create initial entity
    entity = db.add_entity("test_type", "test_entity")
    entity_id = entity.id
    
    try:
        # Attempt an invalid query that will fail
        db.execute_query("INVALID SQL")
    except ValueError:
        pass  # Expected error
    
    # Verify entity still exists after failed query
    retrieved = db.get_entity(entity_id=entity_id)
    assert retrieved is not None
    assert retrieved.id == entity_id
    assert retrieved.type == "test_type"
    assert retrieved.name == "test_entity"

def test_transaction_isolation(db):
    """Test that rollback only affects current transaction."""
    # Create initial entity
    entity1 = db.add_entity("test_type", "entity1")
    
    try:
        # Start a new transaction that will fail
        db.execute_query("INSERT INTO entities (type, name) VALUES ('test_type', 'entity2')")
        db.execute_query("INVALID SQL")  # This will fail
    except ValueError:
        pass  # Expected error
    
    # Verify first entity still exists
    retrieved = db.get_entity(entity_id=entity1.id)
    assert retrieved is not None
    assert retrieved.id == entity1.id
    
    # Create another entity after failed transaction
    entity3 = db.add_entity("test_type", "entity3")
    assert entity3 is not None
    assert entity3.type == "test_type"
    assert entity3.name == "entity3"

def test_connection_recovery_after_errors(db):
    """Test connection recovery after query errors."""
    # Create initial entity
    entity1 = db.add_entity("test_type", "entity1")
    
    # Force multiple failed queries
    for _ in range(3):
        try:
            db.execute_query("INVALID SQL")
        except ValueError:
            pass  # Expected error
    
    # Verify connection still works
    entity2 = db.add_entity("test_type", "entity2")
    assert entity2 is not None
    assert entity2.type == "test_type"
    assert entity2.name == "entity2"
    
    # Verify first entity still exists
    retrieved = db.get_entity(entity_id=entity1.id)
    assert retrieved is not None
    assert retrieved.id == entity1.id

def test_list_tables(db):
    """Test listing database tables."""
    tables = db.list_tables()
    assert isinstance(tables, list)
    # Should have at least our core tables
    table_names = {t['table_name'] for t in tables}
    assert 'entities' in table_names
    assert 'properties' in table_names
    assert 'relationships' in table_names
    
    # Verify structure
    for table in tables:
        assert 'table_name' in table
        assert 'row_count' in table
        assert 'size' in table

def test_describe_table(db):
    """Test describing table structure."""
    # Test entities table
    columns = db.describe_table('entities')
    assert isinstance(columns, list)
    column_names = {c['column_name'] for c in columns}
    assert 'id' in column_names
    assert 'type' in column_names
    assert 'name' in column_names
    assert 'created_at' in column_names
    assert 'last_updated' in column_names
    
    # Verify structure
    for column in columns:
        assert 'column_name' in column
        assert 'data_type' in column
        assert 'is_nullable' in column
        assert 'column_default' in column
        assert 'constraints' in column
    
    # Test invalid table
    with pytest.raises(RuntimeError, match="Failed to describe table"):
        db.describe_table('nonexistent_table')

def test_update_properties(db, test_entity, test_entities):
    """Test update_properties functionality for both entities and relationships."""
    # Get test entities for relationship
    entity1, entity2 = test_entities
    relationship = db.add_relationship(entity1.id, entity2.id, "test_relation")
    
    # Test updating entity properties
    entity_props = {
        "str_prop": "test_value",
        "num_prop": "42",
        "bool_prop": "true"
    }
    db.update_properties(entity_id=test_entity.id, properties=entity_props)
    
    # Verify entity properties
    props = db.get_properties(entity_id=test_entity.id)
    assert len(props) == 3
    prop_dict = {p.key: p.value for p in props}
    assert prop_dict["str_prop"] == "test_value"
    assert prop_dict["num_prop"] == "42"
    assert prop_dict["bool_prop"] == "true"
    
    # Test updating relationship properties
    rel_props = {
        "weight": "0.8",
        "label": "test_label",
        "active": "false"
    }
    db.update_properties(relationship_id=relationship.id, properties=rel_props)
    
    # Verify relationship properties
    props = db.get_properties(relationship_id=relationship.id)
    assert len(props) == 3
    prop_dict = {p.key: p.value for p in props}
    assert prop_dict["weight"] == "0.8"
    assert prop_dict["label"] == "test_label"
    assert prop_dict["active"] == "false"
    
    # Test updating existing properties
    updated_props = {
        "str_prop": "new_value",  # Update existing
        "new_prop": "added"       # Add new
    }
    db.update_properties(entity_id=test_entity.id, properties=updated_props)
    
    # Verify updates
    props = db.get_properties(entity_id=test_entity.id)
    assert len(props) == 4  # Original 3 + 1 new
    prop_dict = {p.key: p.value for p in props}
    assert prop_dict["str_prop"] == "new_value"
    assert prop_dict["new_prop"] == "added"
    
    # Test validation
    with pytest.raises(ValueError, match="Must provide either entity_id or relationship_id"):
        db.update_properties(properties={"key": "value"})
    
    with pytest.raises(ValueError, match="Cannot provide both entity_id and relationship_id"):
        db.update_properties(
            entity_id=test_entity.id,
            relationship_id=relationship.id,
            properties={"key": "value"}
        )
    
    with pytest.raises(ValueError, match="Entity with ID .* not found"):
        db.update_properties(entity_id=99999, properties={"key": "value"})

def test_connection_close(db):
    """Test connection closing behavior."""
    # Test normal close
    db.close()
    assert db.connection.closed
    
    # Test idempotent close
    db.close()  # Should not raise error
