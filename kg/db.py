"""PostgreSQL database manager for the knowledge graph."""

import logging
import os
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import DictCursor

logger = logging.getLogger("kg_access")

class PostgresDB:
    """PostgreSQL database manager for the knowledge graph."""
    def __init__(self, connection_config: dict):
        """Initialize PostgreSQL database connection."""
        required = ['dbname', 'user', 'host', 'port']
        if missing := [k for k in required if not connection_config.get(k)]:
            raise ValueError(f"Missing required parameters: {missing}")
        
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
                self.connection.autocommit = False
                logger.info("PostgreSQL connection established")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to connect: {e}")
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield
            self.connection.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    def execute_query(self, query: str, params: Optional[tuple] = None) -> Optional[List[Dict]]:
        """Execute a query within a transaction.
        
        Args:
            query: SQL query string
            params: Optional tuple of parameters for query
            
        Returns:
            List of dictionaries containing query results, or None for write operations
            
        Raises:
            ConnectionError: If database connection fails
            ValueError: If query is invalid
            RuntimeError: For other database errors
        """
        if not self.connection or self.connection.closed:
            self._init_database()
            
        with self.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                return None

    def close(self):
        """Close the database connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("PostgreSQL connection closed")