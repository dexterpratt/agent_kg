"""PostgreSQL database connection and query execution."""

import logging
from typing import Optional, List, Dict, Any, Union
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.errors import OperationalError, ProgrammingError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("postgres_module")


class PostgresDB:
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
        params: Optional[tuple] = None
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
            raise ValueError(f"Invalid query or parameters: {e}")
        except OperationalError as e:
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
