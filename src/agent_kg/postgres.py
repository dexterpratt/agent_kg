"""PostgreSQL database connection and query execution."""

from typing import Optional, List, Dict, Any, Union
import logging
import select
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Any, Union, Tuple
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.errors import OperationalError, ProgrammingError
from psycopg2.extensions import POLL_OK, POLL_READ, POLL_WRITE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("postgres_module")

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
        """Initialize PostgreSQL database connection.
        
        Args:
            connection_config: Dictionary containing connection parameters
                (dbname, user, password, host, port)
        
        Raises:
            ValueError: If connection configuration is invalid
            ConnectionError: If database connection fails
        """
        if not all(k in connection_config for k in ['dbname', 'user', 'host', 'port']):
            raise ValueError("Invalid connection configuration: missing required parameters")
        
        self.connection_config = connection_config
        self.connection = None
        self._init_database()

    def _init_database(self, max_retries: int = 3) -> None:
        """Initialize connection to the PostgreSQL database with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
        
        Raises:
            ConnectionError: If all connection attempts fail
        """
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
                    raise ConnectionError(f"Failed to connect to PostgreSQL after {max_retries} attempts: {e}")
            except Exception as e:
                raise ConnectionError(f"Unexpected error connecting to PostgreSQL: {e}")

    def execute_query(
        self, 
        query: str, 
        params: Optional[tuple] = None,
        timeout: Optional[float] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute a SQL query and return results as a list of dictionaries.
        
        Args:
            query: SQL query string
            params: Query parameters as a tuple
        
        Returns:
            List of dictionaries for SELECT queries, None for other query types
        
        Raises:
            ValueError: If query is invalid or empty
            DatabaseError: If query execution fails
            ConnectionError: If database connection is lost
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        timeout = timeout or DEFAULT_TIMEOUT

        try:
            if not self.connection or self.connection.closed:
                logger.warning("Connection lost, attempting to reconnect")
                self._init_database()

            with self.connection.cursor() as cursor:
                # Set statement timeout at the session level
                cursor.execute(f"SET statement_timeout = {int(timeout * 1000)}")
                
                cursor.execute(query, params or ())

                # Use select to implement timeout for results
                while True:
                    state = self.connection.poll()
                    if state == POLL_OK:
                        break
                    elif state == POLL_READ:
                        select.select([self.connection], [], [], timeout)
                    elif state == POLL_WRITE:
                        select.select([], [self.connection], [], timeout)
                    else:
                        raise OperationalError("Poll failed")

                if cursor.description:  # SELECT query
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]

                self.connection.commit()  # For INSERT/UPDATE/DELETE
                return None

        except select.error as e:
            raise TimeoutError(f"Query execution timed out after {timeout} seconds")
        except ProgrammingError as e:
            raise ValueError(f"Invalid query or parameters: {e}")
        except OperationalError as e:
            if "statement timeout" in str(e):
                raise TimeoutError(f"Query execution timed out after {timeout} seconds")
            raise ConnectionError(f"Database connection error: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected database error: {e}")

    def close(self) -> None:
        """Close the database connection safely.
        
        This method is idempotent - safe to call multiple times.
        """
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("PostgreSQL connection closed")

    def add_entity(self, type: str, name: str) -> Entity:
        """Add a new entity to the knowledge graph.
        
        Args:
            type: The type of entity
            name: The name of the entity
            
        Returns:
            Entity object with the created entity's data
            
        Raises:
            ValueError: If type or name is invalid
            RuntimeError: If database operation fails
        """
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

    def get_entity(self, entity_id: Optional[int] = None, type: Optional[str] = None, name: Optional[str] = None) -> Optional[Entity]:
        """Retrieve an entity by ID, or type and name.
        
        Args:
            entity_id: The ID of the entity to retrieve
            type: The type of entity to retrieve (used with name)
            name: The name of entity to retrieve (used with type)
            
        Returns:
            Entity object if found, None otherwise
            
        Raises:
            ValueError: If neither entity_id nor both type and name are provided
            RuntimeError: If database operation fails
        """
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

    def update_entity(self, entity_id: int, type: Optional[str] = None, name: Optional[str] = None) -> Optional[Entity]:
        """Update an existing entity.
        
        Args:
            entity_id: The ID of the entity to update
            type: New type for the entity (optional)
            name: New name for the entity (optional)
            
        Returns:
            Updated Entity object if successful, None if entity not found
            
        Raises:
            ValueError: If entity_id is invalid or no updates provided
            RuntimeError: If database operation fails
        """
        if not entity_id:
            raise ValueError("Entity ID is required")
        if type is None and name is None:
            raise ValueError("At least one of type or name must be provided")

        # Build dynamic update query
        update_parts = []
        params = []
        if type is not None:
            if not type.strip():
                raise ValueError("Entity type cannot be empty")
            update_parts.append("type = %s")
            params.append(type)
        if name is not None:
            if not name.strip():
                raise ValueError("Entity name cannot be empty")
            update_parts.append("name = %s")
            params.append(name)
        
        update_parts.append("last_updated = CURRENT_TIMESTAMP")
        params.append(entity_id)

        query = f"""
            UPDATE entities
            SET {", ".join(update_parts)}
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

    def delete_entity(self, entity_id: int) -> bool:
        """Delete an entity from the knowledge graph.
        
        This will also delete all associated properties and relationships
        due to foreign key constraints.
        
        Args:
            entity_id: The ID of the entity to delete
            
        Returns:
            True if entity was deleted, False if entity not found
            
        Raises:
            ValueError: If entity_id is invalid
            RuntimeError: If database operation fails
        """
        if not entity_id:
            raise ValueError("Entity ID is required")

        query = "DELETE FROM entities WHERE id = %s"
        try:
            self.execute_query(query, (entity_id,))
            # Since execute_query returns None for DELETE operations,
            # we need to check if the entity exists first
            check_query = "SELECT EXISTS(SELECT 1 FROM entities WHERE id = %s)"
            result = self.execute_query(check_query, (entity_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete entity: {e}")

    def add_property(self, key: str, value: str, value_type: Union[ValueType, str], 
                    entity_id: Optional[int] = None, relationship_id: Optional[int] = None) -> Property:
        """Add a new property to an entity or relationship.
        
        Args:
            key: Property key
            value: Property value
            value_type: Type of the value (ValueType enum or string name)
            entity_id: ID of the entity to attach property to (optional)
            relationship_id: ID of the relationship to attach property to (optional)
            
        Returns:
            Property object with the created property's data
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If database operation fails
        """
        if not key or not key.strip():
            raise ValueError("Property key cannot be empty")
        if value is None:
            raise ValueError("Property value cannot be None")
        if not (entity_id or relationship_id):
            raise ValueError("Must provide either entity_id or relationship_id")
        if entity_id and relationship_id:
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
                str(value),  # Convert value to string for storage
                value_type.name  # Store enum name
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

    def get_properties(self, entity_id: Optional[int] = None, 
                      relationship_id: Optional[int] = None,
                      key: Optional[str] = None) -> List[Property]:
        """Get properties for an entity or relationship.
        
        Args:
            entity_id: ID of the entity to get properties for (optional)
            relationship_id: ID of the relationship to get properties for (optional)
            key: Filter by property key (optional)
            
        Returns:
            List of Property objects
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If database operation fails
        """
        if entity_id and relationship_id:
            raise ValueError("Cannot provide both entity_id and relationship_id")

        conditions = []
        params = []
        
        if entity_id:
            conditions.append("entity_id = %s")
            params.append(entity_id)
        if relationship_id:
            conditions.append("relationship_id = %s")
            params.append(relationship_id)
        if key:
            conditions.append("key = %s")
            params.append(key)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
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
                    relationship_id=row['relationship_id'],
                    created_at=row['created_at'],
                    last_updated=row['last_updated']
                )
                for row in (result or [])
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get properties: {e}")

    def update_property(self, property_id: int, value: Optional[str] = None, 
                       value_type: Optional[Union[ValueType, str]] = None) -> Optional[Property]:
        """Update an existing property.
        
        Args:
            property_id: ID of the property to update
            value: New value for the property (optional)
            value_type: New value type (optional)
            
        Returns:
            Updated Property object if successful, None if property not found
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If database operation fails
        """
        if not property_id:
            raise ValueError("Property ID is required")
        if value is None and value_type is None:
            raise ValueError("Must provide either value or value_type")

        # Convert string value_type to enum if needed
        if isinstance(value_type, str):
            try:
                value_type = ValueType[value_type.upper()]
            except KeyError:
                raise ValueError(f"Invalid value_type: {value_type}")

        update_parts = []
        params = []
        
        if value is not None:
            update_parts.append("value = %s")
            params.append(str(value))
        if value_type is not None:
            update_parts.append("value_type = %s")
            params.append(value_type.name)
        
        update_parts.append("last_updated = CURRENT_TIMESTAMP")
        params.append(property_id)

        query = f"""
            UPDATE properties
            SET {", ".join(update_parts)}
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
                relationship_id=row['relationship_id'],
                created_at=row['created_at'],
                last_updated=row['last_updated']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update property: {e}")

    def delete_property(self, property_id: int) -> bool:
        """Delete a property.
        
        Args:
            property_id: ID of the property to delete
            
        Returns:
            True if property was deleted, False if property not found
            
        Raises:
            ValueError: If property_id is invalid
            RuntimeError: If database operation fails
        """
        if not property_id:
            raise ValueError("Property ID is required")

        query = "DELETE FROM properties WHERE id = %s"
        try:
            self.execute_query(query, (property_id,))
            check_query = "SELECT EXISTS(SELECT 1 FROM properties WHERE id = %s)"
            result = self.execute_query(check_query, (property_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete property: {e}")

    def add_relationship(self, source_id: int, target_id: int, type: str) -> Relationship:
        """Add a new relationship between entities.
        
        Args:
            source_id: ID of the source entity
            target_id: ID of the target entity
            type: Type of relationship
            
        Returns:
            Relationship object with the created relationship's data
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If database operation fails
        """
        if not source_id:
            raise ValueError("Source entity ID is required")
        if not target_id:
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

    def get_relationships(self, 
                         relationship_id: Optional[int] = None,
                         source_id: Optional[int] = None,
                         target_id: Optional[int] = None,
                         type: Optional[str] = None) -> List[Relationship]:
        """Get relationships based on various filters.
        
        Args:
            relationship_id: ID of specific relationship to get
            source_id: Filter by source entity ID
            target_id: Filter by target entity ID
            type: Filter by relationship type
            
        Returns:
            List of Relationship objects matching the filters
            
        Raises:
            RuntimeError: If database operation fails
        """
        conditions = []
        params = []
        
        if relationship_id:
            conditions.append("id = %s")
            params.append(relationship_id)
        if source_id:
            conditions.append("source_id = %s")
            params.append(source_id)
        if target_id:
            conditions.append("target_id = %s")
            params.append(target_id)
        if type:
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

    def update_relationship(self, relationship_id: int, type: str) -> Optional[Relationship]:
        """Update a relationship's type.
        
        Args:
            relationship_id: ID of the relationship to update
            type: New relationship type
            
        Returns:
            Updated Relationship object if successful, None if relationship not found
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If database operation fails
        """
        if not relationship_id:
            raise ValueError("Relationship ID is required")
        if not type or not type.strip():
            raise ValueError("Relationship type cannot be empty")

        query = """
            UPDATE relationships
            SET type = %s, last_updated = CURRENT_TIMESTAMP
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

    def delete_relationship(self, relationship_id: int) -> bool:
        """Delete a relationship.
        
        This will also delete all associated properties due to foreign key constraints.
        
        Args:
            relationship_id: ID of the relationship to delete
            
        Returns:
            True if relationship was deleted, False if relationship not found
            
        Raises:
            ValueError: If relationship_id is invalid
            RuntimeError: If database operation fails
        """
        if not relationship_id:
            raise ValueError("Relationship ID is required")

        query = "DELETE FROM relationships WHERE id = %s"
        try:
            self.execute_query(query, (relationship_id,))
            check_query = "SELECT EXISTS(SELECT 1 FROM relationships WHERE id = %s)"
            result = self.execute_query(check_query, (relationship_id,))
            return not result[0]['exists']
        except Exception as e:
            raise RuntimeError(f"Failed to delete relationship: {e}")

    def get_entity_relationships(self, entity_id: int, 
                               include_incoming: bool = True,
                               include_outgoing: bool = True,
                               type: Optional[str] = None) -> List[Tuple[Relationship, Entity, Entity]]:
        """Get all relationships involving an entity, along with the connected entities.
        
        Args:
            entity_id: ID of the entity to get relationships for
            include_incoming: Include relationships where entity is the target
            include_outgoing: Include relationships where entity is the source
            type: Filter by relationship type
            
        Returns:
            List of tuples containing (relationship, source_entity, target_entity)
            
        Raises:
            ValueError: If entity_id is invalid or no direction specified
            RuntimeError: If database operation fails
        """
        if not entity_id:
            raise ValueError("Entity ID is required")
        if not (include_incoming or include_outgoing):
            raise ValueError("Must include at least one relationship direction")

        conditions = []
        params = []

        # Build the direction conditions
        direction_conditions = []
        if include_outgoing:
            direction_conditions.append("r.source_id = %s")
            params.append(entity_id)
        if include_incoming:
            direction_conditions.append("r.target_id = %s")
            params.append(entity_id)
        
        if direction_conditions:
            conditions.append(f"({' OR '.join(direction_conditions)})")
        
        if type:
            conditions.append("r.type = %s")
            params.append(type)

        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                r.id, r.source_id, r.target_id, r.type, 
                r.created_at, r.last_updated,
                s.id as source_entity_id, s.type as source_type, 
                s.name as source_name, s.created_at as source_created_at,
                s.last_updated as source_last_updated,
                t.id as target_entity_id, t.type as target_type,
                t.name as target_name, t.created_at as target_created_at,
                t.last_updated as target_last_updated
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
                        id=row['source_entity_id'],
                        type=row['source_type'],
                        name=row['source_name'],
                        created_at=row['source_created_at'],
                        last_updated=row['source_last_updated']
                    ),
                    Entity(
                        id=row['target_entity_id'],
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
