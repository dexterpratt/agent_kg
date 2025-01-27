"""Knowledge Graph Access Server - MCP interface to PostgreSQL knowledge graph."""

import logging
import os
import dotenv
from mcp.server import FastMCP

from kg.db import PostgresDB
from kg.tools.entity import register_entity_tools
from kg.tools.query import register_query_tools

# Initialize logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOGLEVEL', 'INFO')),
    format='%(asctime)s [%(levelname)s] %(message)s - %(filename)s:%(lineno)d'
)
logger = logging.getLogger("kg_access")

# Load environment and initialize database
env_file = ".env.test" if os.getenv("PYTEST_CURRENT_TEST") else ".env.production"
dotenv.load_dotenv(env_file)

db = PostgresDB({
    "dbname": os.getenv("POSTGRES_DB", "memento"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
})

# Create MCP server
mcp = FastMCP("Knowledge Graph Access")

# Register tools
register_entity_tools(mcp, db)
register_query_tools(mcp, db)

if __name__ == "__main__":
    mcp.run()