"""FastMCP server implementation for the knowledge graph."""

import asyncio
import logging
import os
import json
import select
from typing import Dict, Any, Optional, List, Union, Tuple, cast
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum, auto

from mcp.server.fastmcp import FastMCP
import dotenv
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.errors import OperationalError, ProgrammingError
from psycopg2.extensions import POLL_OK, POLL_READ, POLL_WRITE

# Configure logging
log_level = os.getenv('LOGLEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s [%(levelname)s] %(message)s - %(filename)s:%(lineno)d'
)

logger = logging.getLogger("knowledge_graph_server")

def log_db_operation(operation, details=None, error=None):
    """Helper to log database operations with consistent format."""
    msg = f"DB Operation: {operation}"
    if details:
        msg += f" - {details}"
    if error:
        msg += f" - Error: {error}"
    logger.info(msg)

DEFAULT_TIMEOUT = 10  # seconds

class ValueType(Enum):
    """Valid property value types."""
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    DATETIME = auto()
    JSON = auto()

@dataclass
class Relationship:
    """Represents a relationship between entities in the knowledge graph."""
    id: Optional[int]
    source_id: int
    target_id: int
    type: str
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

@dataclass
class Property:
    """Represents a property in the knowledge graph."""
    id: Optional[int]
    key: str
    value: str
    value_type: ValueType
    entity_id: Optional[int] = None
    relationship_id: Optional[int] = None
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

@dataclass
class Entity:
    """Represents an entity in the knowledge graph."""
    id: Optional[int]
    type: str
    name: str
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

class PostgresDB:
    """PostgreSQL database manager for the knowledge graph."""
    def __init__(self, connection_config: dict):
        """Initialize PostgreSQL database connection."""
        required = ['dbname', 'user', 'host', 'port']
        missing = [k for k in required if not connection_config.get(k)]
        if missing:
            raise ValueError("missing required parameters")
        
        self.connection_config = connection_config
        self.connection = None
        self._init_database()

    def _init_database(self, max_retries: int = 3) -> None:
        """Initialize connection to PostgreSQL database with retry logic."""
        for attempt in range(max_retries):
            try:
                self.connection = psycopg2.connect(
                    **self.connection_config, 
                    cursor_factory=DictCursor
                )
                # Default to autocommit=False so write operations are in transactions
                self.connection.autocommit = False
                logger.info("PostgreSQL connection established")
                return
            except OperationalError as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to connect after {max_retries} attempts")
            except Exception as e:
                raise ConnectionError(f"Unexpected connection error: {e}")

    def is_read_only_query(self, query: str) -> bool:
        """Check if a query is read-only (SELECT only).
        
        Args:
            query: SQL query string to validate
            
        Returns:
            True if query is read-only, False otherwise
        """
        # Normalize query by removing comments and extra whitespace
        clean_query = ' '.join(
            line for line in query.split('\n')
            if not line.strip().startswith('--')
        ).strip().upper()
        
        # Check if query starts with SELECT and doesn't contain write operations
        write_operations = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']
        return (
            clean_query.startswith('SELECT') and
            not any(op in clean_query for op in write_operations)
        )

    def execute_query(self, query: str, params: Optional[tuple] = None, enforce_read_only: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Execute a SQL query and return results."""
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
            
        if enforce_read_only and not self.is_read_only_query(query):
            raise ValueError("Only SELECT queries are allowed")

        log_db_operation("Starting query execution", f"Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        try:
            if not self.connection or self.connection.closed:
                logger.warning("Connection lost, attempting to reconnect")
                self._init_database()
                log_db_operation("Connection reinitialized")

            is_read_only = self.is_read_only_query(query)
            
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                log_db_operation("Query executed")

                if cursor.description:  # SELECT query
                    columns = [desc[0] for desc in cursor.description]
                    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    log_db_operation("SELECT results fetched", f"Row count: {len(results)}")
                    if not is_read_only:
                        # If this was a RETURNING clause from a write operation, commit
                        self.connection.commit()
                        log_db_operation("Write transaction committed")
                    return results

                if not is_read_only:
                    # Write operation completed
                    self.connection.commit()
                    log_db_operation("Write transaction committed")
                return None

        except Exception as e:
            log_db_operation("Database Error", error=str(e))
            # Rollback after any error to reset transaction state
            if self.connection and not self.connection.closed:
                self.connection.rollback()
                log_db_operation("Write transaction rolled back")
            
            # Check connection health
            if isinstance(e, (ProgrammingError, OperationalError)):
                try:
                    self.connection.status
                except:
                    self._init_database()
                    log_db_operation("Connection reinitialized after error")
            
            # Raise appropriate error
            if isinstance(e, (ProgrammingError, OperationalError)):
                raise ValueError(f"Query error: {e}")
            raise RuntimeError(f"Unexpected database error: {e}")

    def close(self) -> None:
        """Close the database connection safely."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("PostgreSQL connection closed")

    def add_entity(self, type: str, name: str) -> Entity:
        """Add a new entity to the knowledge graph."""
        if not type or not type.strip():
            raise ValueError("Entity type cannot be empty")
        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")

        log_db_operation("Adding entity", f"type={type}, name={name}")

        query = """
            INSERT INTO entities (type, name)
            VALUES (%s, %s)
            RETURNING id, type, name, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (type, name))
            if not result or len(result) != 1:
                raise RuntimeError("Failed to create entity")
            
            row = result[0]
            entity = Entity(
                id=row['id'],
                type=row['type'],
                name=row['name'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
            log_db_operation("Entity added", f"id={entity.id}")
            return entity
            
        except Exception as e:
            log_db_operation("Add entity failed", error=str(e))
            raise RuntimeError(f"Failed to add entity: {e}")

    def get_entity(self, entity_id: Optional[int] = None, type: Optional[str] = None, name: Optional[str] = None) -> Optional[Entity]:
        """Get an entity by ID or type/name combination."""
        if entity_id is None and (type is None or name is None):
            raise ValueError("Must provide either entity_id or both type and name")

        if entity_id is not None:
            query = """
                SELECT id, type, name, created_at, last_updated
                FROM entities
                WHERE id = %s
            """
            params = (entity_id,)
        else:
            query = """
                SELECT id, type, name, created_at, last_updated
                FROM entities
                WHERE type = %s AND name = %s
            """
            params = (type, name)

        try:
            result = self.execute_query(query, params)
            if not result:
                return None
            
            row = result[0]
            return Entity(
                id=row['id'],
                type=row['type'],
                name=row['name'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to get entity: {e}")

    def update_entity(self, entity_id: Optional[int], type: Optional[str] = None, name: Optional[str] = None) -> Optional[Entity]:
        """Update an entity's type and/or name."""
        if entity_id is None:
            raise ValueError("Entity ID is required")
        if type is None and name is None:
            raise ValueError("At least one of type or name must be provided")
        if type == "":
            raise ValueError("Entity type cannot be empty")
        if name == "":
            raise ValueError("Entity name cannot be empty")

        # Build update query dynamically based on provided fields
        update_fields = []
        params = []
        if type is not None:
            update_fields.append("type = %s")
            params.append(type)
        if name is not None:
            update_fields.append("name = %s")
            params.append(name)
        
        update_fields.append("last_updated = clock_timestamp()")
        params.append(entity_id)  # For WHERE clause

        query = f"""
            UPDATE entities 
            SET {", ".join(update_fields)}
            WHERE id = %s
            RETURNING id, type, name, created_at, last_updated
        """

        try:
            result = self.execute_query(query, tuple(params))
            if not result:
                return None
            
            row = result[0]
            return Entity(
                id=row['id'],
                type=row['type'],
                name=row['name'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update entity: {e}")

    def delete_entity(self, entity_id: Optional[int]) -> bool:
        """Delete an entity and its properties."""
        if entity_id is None:
            raise ValueError("Entity ID is required")

        try:
            # Delete properties first
            self.execute_query("DELETE FROM properties WHERE entity_id = %s", (entity_id,))
            
            # Delete relationships
            self.execute_query("DELETE FROM relationships WHERE source_id = %s OR target_id = %s", (entity_id, entity_id))
            
            # Delete entity
            self.execute_query("DELETE FROM entities WHERE id = %s", (entity_id,))
            
            # Verify deletion
            check_query = "SELECT EXISTS(SELECT 1 FROM entities WHERE id = %s)"
            result = self.execute_query(check_query, (entity_id,))
            
            # Commit transaction if verification succeeds
            self.connection.commit()
            return not result[0]['exists']
            
        except Exception as e:
            # Rollback on any error
            if self.connection and not self.connection.closed:
                self.connection.rollback()
            raise RuntimeError(f"Failed to delete entity: {e}")

    def add_property(self, key: str, value: str, value_type: Union[ValueType, str], entity_id: Optional[int] = None, relationship_id: Optional[int] = None) -> Property:
        """Add a property to an entity or relationship."""
        if not key or not key.strip():
            raise ValueError("Property key cannot be empty")
        if value is None:
            raise ValueError("Property value cannot be None")
        if entity_id is None and relationship_id is None:
            raise ValueError("Must provide either entity_id or relationship_id")
        if entity_id is not None and relationship_id is not None:
            raise ValueError("Cannot provide both entity_id and relationship_id")
            
        # Convert string value_type to enum if needed
        if isinstance(value_type, str):
            try:
                value_type = ValueType[value_type.upper()]
            except KeyError:
                raise ValueError(f"Invalid value_type: {value_type}")
        query = """
            INSERT INTO properties (entity_id, relationship_id, key, value, value_type)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, entity_id, relationship_id, key, value, value_type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (
                entity_id,
                relationship_id,
                key,
                str(value),
                value_type.name if isinstance(value_type, ValueType) else ValueType[value_type.upper()].name
            ))
            if not result or len(result) != 1:
                raise RuntimeError("Failed to create property")
            
            row = result[0]
            return Property(
                id=row['id'],
                key=row['key'],
                value=row['value'],
                value_type=ValueType[row['value_type']],
                entity_id=row['entity_id'],
                relationship_id=row['relationship_id'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to add property: {e}")

    def get_properties(self, entity_id: Optional[int] = None, relationship_id: Optional[int] = None, key: Optional[str] = None) -> List[Property]:
        """Get properties for an entity or relationship."""
        if entity_id is None and relationship_id is None:
            raise ValueError("Must provide either entity_id or relationship_id")
        if entity_id is not None and relationship_id is not None:
            raise ValueError("Cannot provide both entity_id and relationship_id")

        conditions = []
        params = []
        
        if entity_id is not None:
            conditions.append("entity_id = %s")
            params.append(entity_id)
        if relationship_id is not None:
            conditions.append("relationship_id = %s")
            params.append(relationship_id)
        
        if key:
            conditions.append("key = %s")
            params.append(key)

        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT id, entity_id, relationship_id, key, value, value_type, created_at, last_updated
            FROM properties
            WHERE {where_clause}
            ORDER BY key, created_at
        """
        
        try:
            result = self.execute_query(query, tuple(params))
            return [
                Property(
                    id=row['id'],
                    key=row['key'],
                    value=row['value'],
                    value_type=ValueType[row['value_type']],
                    entity_id=row['entity_id'],
                    created_at=row['created_at'],
                    last_updated=row['last_updated']
                )
                for row in (result or [])
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get properties: {e}")

    def update_property(self, property_id: Optional[int], value: Optional[str] = None, value_type: Optional[ValueType] = None) -> Optional[Property]:
        """Update a property's value and/or value type."""
        if property_id is None:
            raise ValueError("Property ID is required")
        if value is None and value_type is None:
            raise ValueError("Must provide either value or value_type")

        # Build update query dynamically based on provided fields
        update_fields = []
        params = []
        if value is not None:
            update_fields.append("value = %s")
            params.append(str(value))
        if value_type is not None:
            update_fields.append("value_type = %s")
            params.append(value_type.name)
        
        update_fields.append("last_updated = clock_timestamp()")
        params.append(property_id)  # For WHERE clause

        query = f"""
            UPDATE properties
            SET {", ".join(update_fields)}
            WHERE id = %s
            RETURNING id, entity_id, relationship_id, key, value, value_type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, tuple(params))
            if not result:
                return None
            
            row = result[0]
            return Property(
                id=row['id'],
                key=row['key'],
                value=row['value'],
                value_type=ValueType[row['value_type']],
                entity_id=row['entity_id'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update property: {e}")

    def delete_property(self, property_id: Optional[int]) -> bool:
        """Delete a property."""
        if property_id is None:
            raise ValueError("Property ID is required")

        query = "DELETE FROM properties WHERE id = %s"
        try:
            self.execute_query(query, (property_id,))
            check_query = "SELECT EXISTS(SELECT 1 FROM properties WHERE id = %s)"
            result = self.execute_query(check_query, (property_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete property: {e}")

    def add_relationship(self, source_id: Optional[int], target_id: Optional[int], type: str) -> Relationship:
        """Add a new relationship between entities."""
        if source_id is None:
            raise ValueError("Source entity ID is required")
        if target_id is None:
            raise ValueError("Target entity ID is required")
        if not type or not type.strip():
            raise ValueError("Relationship type cannot be empty")

        query = """
            INSERT INTO relationships (source_id, target_id, type)
            VALUES (%s, %s, %s)
            RETURNING id, source_id, target_id, type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (source_id, target_id, type))
            if not result or len(result) != 1:
                raise RuntimeError("Failed to create relationship")
            
            row = result[0]
            return Relationship(
                id=row['id'],
                source_id=row['source_id'],
                target_id=row['target_id'],
                type=row['type'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to add relationship: {e}")

    def get_relationships(self, source_id: Optional[int] = None, target_id: Optional[int] = None, type: Optional[str] = None) -> List[Relationship]:
        """Get relationships with optional filters."""
        conditions = []
        params = []
        
        if source_id is not None:
            conditions.append("source_id = %s")
            params.append(source_id)
        if target_id is not None:
            conditions.append("target_id = %s")
            params.append(target_id)
        if type is not None:
            conditions.append("type = %s")
            params.append(type)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
            SELECT id, source_id, target_id, type, created_at, last_updated
            FROM relationships
            WHERE {where_clause}
            ORDER BY created_at
        """
        
        try:
            result = self.execute_query(query, tuple(params))
            return [
                Relationship(
                    id=row['id'],
                    source_id=row['source_id'],
                    target_id=row['target_id'],
                    type=row['type'],
                    created_at=row['created_at'],
                    last_updated=row['last_updated']
                )
                for row in (result or [])
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get relationships: {e}")

    def update_relationship(self, relationship_id: Optional[int], type: str) -> Optional[Relationship]:
        """Update a relationship's type."""
        if relationship_id is None:
            raise ValueError("Relationship ID is required")
        if not type or not type.strip():
            raise ValueError("Relationship type cannot be empty")

        query = """
            UPDATE relationships
            SET type = %s, last_updated = clock_timestamp()
            WHERE id = %s
            RETURNING id, source_id, target_id, type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (type, relationship_id))
            if not result:
                return None
            
            row = result[0]
            return Relationship(
                id=row['id'],
                source_id=row['source_id'],
                target_id=row['target_id'],
                type=row['type'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update relationship: {e}")

    def delete_relationship(self, relationship_id: Optional[int]) -> bool:
        """Delete a relationship."""
        if relationship_id is None:
            raise ValueError("Relationship ID is required")

        query = "DELETE FROM relationships WHERE id = %s"
        try:
            self.execute_query(query, (relationship_id,))
            check_query = "SELECT EXISTS(SELECT 1 FROM relationships WHERE id = %s)"
            result = self.execute_query(check_query, (relationship_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete relationship: {e}")

    def list_tables(self) -> List[Dict[str, Any]]:
        """Get list of all tables in the database.
        
        Returns:
            List of dicts containing table information:
            - table_name: Name of the table
            - row_count: Approximate number of rows
            - size: Size of table in bytes
        """
        query = """
            SELECT 
                t.table_name,
                (SELECT reltuples::bigint FROM pg_class c WHERE c.relname = t.table_name) as row_count,
                pg_total_relation_size(quote_ident(t.table_name)) as size
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        try:
            return self.execute_query(query) or []
        except Exception as e:
            raise RuntimeError(f"Failed to list tables: {e}")
            
    def describe_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Get detailed information about a table's columns.
        
        Args:
            table_name: Name of the table to describe
            
        Returns:
            List of dicts containing column information:
            - column_name: Name of the column
            - data_type: PostgreSQL data type
            - is_nullable: Whether column can be NULL
            - column_default: Default value if any
            - constraints: Any constraints on the column
            
        Raises:
            RuntimeError: If table doesn't exist or other error occurs
        """
        # First verify table exists
        check_query = """
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            )
        """
        try:
            result = self.execute_query(check_query, (table_name,))
            if not result or not result[0]['exists']:
                raise RuntimeError(f"Failed to describe table {table_name}: table does not exist")
        except Exception as e:
            raise RuntimeError(f"Failed to describe table {table_name}: {e}")

        # Get column information
        query = """
            SELECT 
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                (
                    SELECT string_agg(DISTINCT tc.constraint_type, ', ')
                    FROM information_schema.constraint_column_usage ccu
                    JOIN information_schema.table_constraints tc 
                        ON tc.constraint_name = ccu.constraint_name
                    WHERE ccu.table_name = c.table_name 
                    AND ccu.column_name = c.column_name
                ) as constraints
            FROM information_schema.columns c
            WHERE c.table_name = %s
            AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
        """
        try:
            return self.execute_query(query, (table_name,)) or []
        except Exception as e:
            raise RuntimeError(f"Failed to describe table {table_name}: {e}")

    def get_entity_relationships(self, entity_id: Optional[int], include_incoming: bool = True, include_outgoing: bool = True, type: Optional[str] = None) -> List[Tuple[Relationship, Entity, Entity]]:
        """Get relationships for an entity with optional direction and type filters."""
        if entity_id is None:
            raise ValueError("Entity ID is required")
        if not include_incoming and not include_outgoing:
            raise ValueError("Must include at least one relationship direction")

        conditions = []
        params = []

        # Build direction conditions
        direction_conditions = []
        if include_outgoing:
            direction_conditions.append("r.source_id = %s")
            params.append(entity_id)
        if include_incoming:
            direction_conditions.append("r.target_id = %s")
            params.append(entity_id)
        
        if direction_conditions:
            conditions.append(f"({' OR '.join(direction_conditions)})")

        # Add type filter if provided
        if type is not None:
            conditions.append("r.type = %s")
            params.append(type)

        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                r.id, r.source_id, r.target_id, r.type, r.created_at, r.last_updated,
                s.id as source_id, s.type as source_type, s.name as source_name, 
                s.created_at as source_created_at, s.last_updated as source_last_updated,
                t.id as target_id, t.type as target_type, t.name as target_name,
                t.created_at as target_created_at, t.last_updated as target_last_updated
            FROM relationships r
            JOIN entities s ON r.source_id = s.id
            JOIN entities t ON r.target_id = t.id
            WHERE {where_clause}
            ORDER BY r.created_at
        """
        
        try:
            result = self.execute_query(query, tuple(params))
            return [
                (
                    Relationship(
                        id=row['id'],
                        source_id=row['source_id'],
                        target_id=row['target_id'],
                        type=row['type'],
                        created_at=row['created_at'],
                        last_updated=row['last_updated']
                    ),
                    Entity(
                        id=row['source_id'],
                        type=row['source_type'],
                        name=row['source_name'],
                        created_at=row['source_created_at'],
                        last_updated=row['source_last_updated']
                    ),
                    Entity(
                        id=row['target_id'],
                        type=row['target_type'],
                        name=row['target_name'],
                        created_at=row['target_created_at'],
                        last_updated=row['target_last_updated']
                    )
                )
                for row in (result or [])
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get entity relationships: {e}")

# Load environment variables and initialize database
env_file = ".env.test" if os.getenv("PYTEST_CURRENT_TEST") else ".env.production"
dotenv.load_dotenv(env_file)

db = PostgresDB({
    "dbname": os.getenv("POSTGRES_DB", "memento"),  # No default - must be specified in env file
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
})

logger.info(f"Connected to database: {os.getenv('POSTGRES_DB')}")

# Create MCP server and define tools
mcp = FastMCP("Agent Knowledge Graph")

@mcp.tool()
async def add_entity(type: str, name: str, properties: Dict[str, Any] = {}) -> str:
    """Add a new entity to the graph with optional properties.
    
    Args:
        type: The type of entity
        name: The name of the entity
        properties: Optional dictionary of property key-value pairs
        
    Returns:
        JSON response containing the created entity details
    """
    try:
        # Create entity
        entity = db.add_entity(type, name)
        
        # Add properties if provided
        for key, value in properties.items():
            db.add_property(
                key=key,
                value=str(value),
                value_type=ValueType.STRING,
                entity_id=entity.id
            )
        
        # Convert entity to dict for JSON serialization
        result = asdict(entity)
        result['created_at'] = result['created_at'].isoformat()
        result['last_updated'] = result['last_updated'].isoformat()
        
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error adding entity: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def update_properties(entity_id: Optional[int] = None, relationship_id: Optional[int] = None, properties: Dict[str, Any] = {}) -> str:
    """Update properties for an entity or relationship.
    
    Args:
        entity_id: Optional ID of entity to update properties for
        relationship_id: Optional ID of relationship to update properties for
        properties: Dictionary of property key-value pairs to update
        
    Returns:
        JSON response indicating success
    """
    try:
        # Validate input
        if entity_id is None and relationship_id is None:
            raise ValueError("Must provide either entity_id or relationship_id")
        if entity_id is not None and relationship_id is not None:
            raise ValueError("Cannot provide both entity_id and relationship_id")
            
        # Verify entity/relationship exists
        if entity_id is not None:
            entity = db.get_entity(entity_id=entity_id)
            if not entity:
                raise ValueError(f"Entity with ID {entity_id} not found")
        
        # Update properties
        for key, value in properties.items():
            existing = db.get_properties(entity_id=entity_id, relationship_id=relationship_id, key=key)
            if existing:
                db.update_property(existing[0].id, value=str(value))
            else:
                db.add_property(
                    key=key,
                    value=str(value),
                    value_type=ValueType.STRING,
                    entity_id=entity_id,
                    relationship_id=relationship_id
                )
        
        return json.dumps({"success": True})
    except Exception as e:
        logger.error(f"Error updating properties: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def delete_entity(id: int) -> str:
    """Delete an entity and all its properties.
    
    Args:
        id: The ID of the entity to delete
        
    Returns:
        JSON response indicating success
    """
    try:
        success = db.delete_entity(id)
        if not success:
            raise ValueError(f"Entity with ID {id} not found")
        return json.dumps({"success": True})
    except Exception as e:
        logger.error(f"Error deleting entity: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def list_knowledge_graph_tables() -> str:
    """List all tables in the knowledge graph database with their sizes and row counts.
    
    Returns:
        JSON response containing table information:
        - table_name: Name of the table
        - row_count: Approximate number of rows
        - size: Size of table in bytes
        
    Example response:
        {
            "success": true,
            "tables": [
                {
                    "table_name": "entities",
                    "row_count": 1000,
                    "size": 524288
                },
                ...
            ]
        }
    """
    try:
        tables = db.list_tables()
        return json.dumps({
            "success": True,
            "tables": tables
        })
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })

@mcp.tool()
async def describe_knowledge_graph_table(table_name: str) -> str:
    """Get detailed information about the columns and constraints in the tables in the knowledge graph database.
    
    Args:
        table_name: Name of the table to describe
        
    Returns:
        JSON response containing column information:
        - column_name: Name of the column
        - data_type: PostgreSQL data type
        - is_nullable: Whether column can be NULL
        - column_default: Default value if any
        - constraints: Any constraints on the column
        
    Example response:
        {
            "success": true,
            "columns": [
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": "nextval('entities_id_seq'::regclass)",
                    "constraints": "PRIMARY KEY"
                },
                ...
            ]
        }
    """
    try:
        columns = db.describe_table(table_name)
        return json.dumps({
            "success": True,
            "columns": columns
        })
    except Exception as e:
        logger.error(f"Error describing table {table_name}: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })

@mcp.tool()
async def add_relationship(source_id: int, target_id: int, type: str, properties: Dict[str, Any] = {}) -> str:
    """Add a new relationship between entities with optional properties.
    
    Args:
        source_id: ID of the source entity
        target_id: ID of the target entity
        type: Type of relationship
        properties: Optional dictionary of property key-value pairs
        
    Returns:
        JSON response containing the created relationship details
    """
    try:
        # Create relationship
        relationship = db.add_relationship(source_id, target_id, type)
        
        # Add properties if provided
        for key, value in properties.items():
            db.add_property(
                key=key,
                value=str(value),
                value_type=ValueType.STRING,
                relationship_id=relationship.id
            )
        
        # Convert relationship to dict for JSON serialization
        result = asdict(relationship)
        result['created_at'] = result['created_at'].isoformat()
        result['last_updated'] = result['last_updated'].isoformat()
        
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error adding relationship: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def update_relationship(id: int, type: str) -> str:
    """Update a relationship's type.
    
    Args:
        id: The ID of the relationship to update
        type: New relationship type
        
    Returns:
        JSON response containing the updated relationship details
    """
    try:
        relationship = db.update_relationship(id, type)
        if not relationship:
            raise ValueError(f"Relationship with ID {id} not found")
            
        result = asdict(relationship)
        result['created_at'] = result['created_at'].isoformat()
        result['last_updated'] = result['last_updated'].isoformat()
        
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error updating relationship: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def delete_relationship(id: int) -> str:
    """Delete a relationship.
    
    Args:
        id: The ID of the relationship to delete
        
    Returns:
        JSON response indicating success
    """
    try:
        success = db.delete_relationship(id)
        if not success:
            raise ValueError(f"Relationship with ID {id} not found")
        return json.dumps({"success": True})
    except Exception as e:
        logger.error(f"Error deleting relationship: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def get_relationships(source_id: Optional[int] = None, target_id: Optional[int] = None, type: Optional[str] = None) -> str:
    """Get relationships with optional filters.
    
    Args:
        source_id: Optional ID of source entity to filter by
        target_id: Optional ID of target entity to filter by
        type: Optional relationship type to filter by
        
    Returns:
        JSON response containing list of relationships
    """
    try:
        relationships = db.get_relationships(source_id, target_id, type)
        result = []
        for rel in relationships:
            rel_dict = asdict(rel)
            rel_dict['created_at'] = rel_dict['created_at'].isoformat()
            rel_dict['last_updated'] = rel_dict['last_updated'].isoformat()
            result.append(rel_dict)
            
        return json.dumps({"relationships": result})
    except Exception as e:
        logger.error(f"Error getting relationships: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def get_entity_relationships(
    entity_id: int,
    include_incoming: bool = True,
    include_outgoing: bool = True,
    type: Optional[str] = None
) -> str:
    """Get relationships for an entity with optional direction and type filters.
    
    Args:
        entity_id: ID of the entity
        include_incoming: Whether to include incoming relationships
        include_outgoing: Whether to include outgoing relationships
        type: Optional relationship type to filter by
        
    Returns:
        JSON response containing list of relationships with connected entities
    """
    try:
        relationships = db.get_entity_relationships(
            entity_id,
            include_incoming=include_incoming,
            include_outgoing=include_outgoing,
            type=type
        )
        
        result = []
        for rel, source, target in relationships:
            item = {
                "relationship": asdict(rel),
                "source": asdict(source),
                "target": asdict(target)
            }
            # Convert datetime objects
            item["relationship"]["created_at"] = item["relationship"]["created_at"].isoformat()
            item["relationship"]["last_updated"] = item["relationship"]["last_updated"].isoformat()
            item["source"]["created_at"] = item["source"]["created_at"].isoformat()
            item["source"]["last_updated"] = item["source"]["last_updated"].isoformat()
            item["target"]["created_at"] = item["target"]["created_at"].isoformat()
            item["target"]["last_updated"] = item["target"]["last_updated"].isoformat()
            result.append(item)
            
        return json.dumps({"relationships": result})
    except Exception as e:
        logger.error(f"Error getting entity relationships: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def get_properties(entity_id: Optional[int] = None, relationship_id: Optional[int] = None, key: Optional[str] = None) -> str:
    """Get properties for an entity or relationship.
    
    Args:
        entity_id: Optional ID of entity to get properties for
        relationship_id: Optional ID of relationship to get properties for
        key: Optional property key to filter by
        
    Returns:
        JSON response containing list of properties
    """
    try:
        properties = db.get_properties(entity_id, relationship_id, key)
        result = []
        for prop in properties:
            prop_dict = asdict(prop)
            prop_dict['created_at'] = prop_dict['created_at'].isoformat()
            prop_dict['last_updated'] = prop_dict['last_updated'].isoformat()
            prop_dict['value_type'] = prop_dict['value_type'].name
            result.append(prop_dict)
            
        return json.dumps({"properties": result})
    except Exception as e:
        logger.error(f"Error getting properties: {e}")
        raise ValueError(str(e))

@mcp.tool()
async def query_knowledge_graph_database(sql: str) -> str:
    """Execute a read-only SQL query against the knowledge graph database.
    
    Args:
        sql: SQL query to execute (must be SELECT only)
        
    Returns:
        JSON response containing query results or error message
        
    Example queries:
        - List tables: SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'
        - List columns: SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'entities'
        - Query entities: SELECT * FROM entities WHERE type = 'person'
        - Join example: SELECT e.*, p.key, p.value FROM entities e LEFT JOIN properties p ON e.id = p.entity_id
    """
    try:
        # Log the query for debugging
        logger.info(f"Executing query: {sql}")
        
        # Execute query with read-only enforcement
        # Check if query contains LIKE and convert to parameterized query
        if 'LIKE' in sql.upper():
            # Extract the LIKE pattern
            import re
            pattern = re.search(r"LIKE\s+'([^']+)'", sql, re.IGNORECASE)
            if pattern:
                like_pattern = pattern.group(1)
                # Replace the literal pattern with a parameter placeholder
                sql = re.sub(r"LIKE\s+'[^']+'", "LIKE %s", sql, flags=re.IGNORECASE)
                results = db.execute_query(sql, (like_pattern,), enforce_read_only=True)
            else:
                results = db.execute_query(sql, enforce_read_only=True)
        else:
            results = db.execute_query(sql, enforce_read_only=True)
        
        # Handle NULL result for empty result sets
        if results is None:
            logger.info("Query returned no results")
            return json.dumps({
                "success": True,
                "results": []
            })
            
        # Convert datetime objects to ISO format strings for JSON serialization
        for row in results:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
        
        logger.info(f"Query returned {len(results)} results")
        return json.dumps({
            "success": True,
            "results": results
        })
        
    except ValueError as e:
        # Handle specific database errors
        error_msg = str(e)
        logger.error(f"Query validation error: {error_msg}")
        return json.dumps({
            "success": False,
            "error": error_msg
        })
    except Exception as e:
        # Handle unexpected errors
        error_msg = str(e)
        logger.error(f"Unexpected query error: {error_msg}")
        
        # Clear the aborted transaction state so future queries can succeed
        if db.connection and not db.connection.closed:
            try:
                # Rollback just clears the failed transaction
                # It does not affect data from previous successful transactions
                db.connection.rollback()
                logger.info("Transaction rolled back - connection ready for new queries")
            except Exception as rollback_error:
                logger.error(f"Could not rollback transaction: {rollback_error}")
        
        return json.dumps({
            "success": False,
            "error": error_msg
        })

if __name__ == "__main__":
    mcp.run()
