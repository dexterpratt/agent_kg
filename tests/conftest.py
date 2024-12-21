"""Shared test fixtures and configuration."""

import os
import pytest
import pytest_asyncio
import asyncio
import logging
from typing import AsyncGenerator, Generator
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

from src.agent_kg.postgres import PostgresDB
from src.agent_kg.server import KnowledgeGraphServer
from src.agent_kg.handlers import ToolHandlers

# Load test environment variables
load_dotenv('.env.test')

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_knowledge_graph")

@pytest.fixture(scope="session")
def test_db_config() -> dict:
    """Get test database configuration from environment."""
    return {
        "dbname": os.getenv("POSTGRES_DB", "memento_test"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
    }

@pytest.fixture(scope="session", autouse=True)
def setup_test_db(test_db_config: dict) -> Generator[None, None, None]:
    """Create and setup test database."""
    admin_config = test_db_config.copy()
    admin_config["dbname"] = "postgres"  # Connect to default db to create test db
    
    # Create test database
    conn = psycopg2.connect(**admin_config)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    dbname = test_db_config["dbname"]
    
    try:
        # Create database
        cursor.execute(f"DROP DATABASE IF EXISTS {dbname}")
        cursor.execute(f"CREATE DATABASE {dbname}")
        logger.info(f"Created test database: {dbname}")
    finally:
        cursor.close()
        conn.close()

    # Initialize schema
    db = PostgresDB(test_db_config)
    try:
        with open('schema.sq', 'r') as f:
            schema_sql = f.read()
            db.execute_query(schema_sql)
        logger.info("Initialized test database schema")
        
        yield
    finally:
        # Close schema initialization connection
        db.close()
        logger.info("Closed schema initialization connection")
        
        # Cleanup - terminate existing connections to the test database
        conn = psycopg2.connect(**admin_config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        try:
            # Terminate all other connections
            cursor.execute(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{dbname}'
                AND pid <> pg_backend_pid()
            """)
            # Now safe to drop the database
            cursor.execute(f"DROP DATABASE IF EXISTS {dbname}")
            logger.info(f"Dropped test database: {dbname}")
        finally:
            cursor.close()
            conn.close()

@pytest.fixture(scope="function")
def db(test_db_config: dict) -> Generator[PostgresDB, None, None]:
    """Provide a database connection for each test."""
    db = PostgresDB(test_db_config)
    yield db
    db.close()

@pytest_asyncio.fixture(scope="function")
async def server(db: PostgresDB) -> AsyncGenerator[KnowledgeGraphServer, None]:
    """Provide a server instance for each test."""
    server = KnowledgeGraphServer()
    
    try:
        # Override production database with test database
        server.db = db
        # Initialize handlers with test database
        server.handlers = ToolHandlers(server.db)
        # Set up tool handlers
        server.setup_tool_handlers()
        
        yield server
    finally:
        try:
            await server.cleanup()
        except Exception as e:
            logger.error(f"Error during server cleanup: {e}")

@pytest.fixture(scope="function")
def clean_db(db: PostgresDB) -> Generator[PostgresDB, None, None]:
    """Provide a clean database state for each test."""
    tables = [
        "properties",
        "validated_properties",
        "relationships",
        "entities",
        "property_definitions",
        "context_entries",
        "context_categories",
        "operation_states",
        "operation_log",
    ]
    
    for table in tables:
        db.execute_query(f"DELETE FROM {table}")
    
    yield db