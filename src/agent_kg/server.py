"""FastMCP server implementation for the knowledge graph."""

import asyncio
import logging
import os
import json
import select
from typing import Dict, Any, Optional, List, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum, auto

from fastmcp import FastMCP
import dotenv
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.errors import OperationalError, ProgrammingError
from psycopg2.extensions import POLL_OK, POLL_READ, POLL_WRITE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("knowledge_graph_server")

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
        if not all(k in connection_config for k in ['dbname', 'user', 'host', 'port']):
            raise ValueError("Invalid connection configuration")
        
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

        try:
            if not self.connection or self.connection.closed:
                logger.warning("Connection lost, attempting to reconnect")
                self._init_database()

            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())

                if cursor.description:  # SELECT query
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]

                self.connection.commit()  # For INSERT/UPDATE/DELETE
                return None

        except ProgrammingError as e:
            self.connection.rollback()  # Rollback transaction on error
            raise ValueError(f"Invalid query or parameters: {e}")
        except OperationalError as e:
            self.connection.rollback()  # Rollback transaction on error
            raise ConnectionError(f"Database connection error: {e}")
        except Exception as e:
            self.connection.rollback()  # Rollback transaction on error
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
            return Entity(
                id=row['id'],
                type=row['type'],
                name=row['name'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to add entity: {e}")

    def get_entity(self, entity_id: int) -> Optional[Entity]:
        """Get an entity by ID."""
        query = """
            SELECT id, type, name, created_at, last_updated
            FROM entities
            WHERE id = %s
        """
        try:
            result = self.execute_query(query, (entity_id,))
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

    def delete_entity(self, entity_id: int) -> bool:
        """Delete an entity and its properties."""
        query = "DELETE FROM entities WHERE id = %s"
        try:
            self.execute_query(query, (entity_id,))
            check_query = "SELECT EXISTS(SELECT 1 FROM entities WHERE id = %s)"
            result = self.execute_query(check_query, (entity_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete entity: {e}")

    def add_property(self, key: str, value: str, value_type: ValueType, entity_id: int) -> Property:
        """Add a property to an entity."""
        query = """
            INSERT INTO properties (entity_id, key, value, value_type)
            VALUES (%s, %s, %s, %s)
            RETURNING id, entity_id, key, value, value_type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (
                entity_id,
                key,
                str(value),
                value_type.name
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
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to add property: {e}")

    def get_properties(self, entity_id: int, key: Optional[str] = None) -> List[Property]:
        """Get properties for an entity."""
        conditions = ["entity_id = %s"]
        params = [entity_id]
        
        if key:
            conditions.append("key = %s")
            params.append(key)

        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT id, entity_id, key, value, value_type, created_at, last_updated
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

    def update_property(self, property_id: int, value: str) -> Optional[Property]:
        """Update a property's value."""
        query = """
            UPDATE properties
            SET value = %s, last_updated = clock_timestamp()
            WHERE id = %s
            RETURNING id, entity_id, key, value, value_type, created_at, last_updated
        """
        try:
            result = self.execute_query(query, (str(value), property_id))
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

# Load environment variables and initialize database
dotenv.load_dotenv()

db = PostgresDB({
    "dbname": os.getenv("POSTGRES_DB", "memento"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
})

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
async def update_entity(id: int, properties: Dict[str, Any]) -> str:
    """Update an entity's properties.
    
    Args:
        id: The ID of the entity to update
        properties: Dictionary of property key-value pairs to update
        
    Returns:
        JSON response indicating success
    """
    try:
        # Verify entity exists
        entity = db.get_entity(entity_id=id)
        if not entity:
            raise ValueError(f"Entity with ID {id} not found")
        
        # Update properties
        for key, value in properties.items():
            existing = db.get_properties(entity_id=id, key=key)
            if existing:
                db.update_property(existing[0].id, value=str(value))
            else:
                db.add_property(
                    key=key,
                    value=str(value),
                    value_type=ValueType.STRING,
                    entity_id=id
                )
        
        return json.dumps({"success": True})
    except Exception as e:
        logger.error(f"Error updating entity: {e}")
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
async def query(sql: str) -> str:
    """Execute a read-only SQL query against the database.
    
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
        # Execute query with read-only enforcement
        results = db.execute_query(sql, enforce_read_only=True)
        
        # Handle NULL result for empty result sets
        if results is None:
            results = []
            
        # Convert datetime objects to ISO format strings for JSON serialization
        for row in results:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
        
        return json.dumps({
            "success": True,
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Query error: {e}")
        
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
            "error": str(e)
        })
