"""FastMCP server implementation for the knowledge graph."""

import asyncio
import logging
import os
from datetime import datetime
import json
from typing import Dict, Any

from fastmcp import FastMCP
import dotenv

from agent_kg.postgres import PostgresDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("knowledge_graph_server")

# Load environment variables
dotenv.load_dotenv()

# Initialize database connection
db = PostgresDB({
    "dbname": os.getenv("POSTGRES_DB", "memento"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
})

# Create MCP server
mcp = FastMCP("Agent Knowledge Graph")

# Tool implementations
@mcp.tool()
async def add_entity(type: str, name: str, properties: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Add a new entity to the graph"""
    try:
        result = db.add_entity(
            entity_type=type,
            name=name,
            properties=properties
        )
        return result
    except Exception as e:
        logger.error(f"Error adding entity: {e}")
        raise

@mcp.tool()
async def update_entity(id: int, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Update an entity's properties"""
    try:
        result = db.update_entity(
            entity_id=id,
            properties=properties
        )
        return result
    except Exception as e:
        logger.error(f"Error updating entity: {e}")
        raise

@mcp.tool()
async def delete_entity(id: int) -> Dict[str, Any]:
    """Delete an entity"""
    try:
        result = db.delete_entity(entity_id=id)
        return result
    except Exception as e:
        logger.error(f"Error deleting entity: {e}")
        raise

# TODO
# select_entity_by_id (id, properties)
# select_entity_by_properties ()
async def cleanup():
    """Clean up server resources."""
    try:
        if db:
            db.close()
        logger.info("Server resources cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during server cleanup: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(mcp.run_stdio_async())
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        raise
    finally:
        asyncio.run(cleanup())
