"""Knowledge Graph MCP Server Package.

This package provides a Model Context Protocol (MCP) server implementation
for managing a knowledge graph with support for entities, relationships,
and contextual information stored in PostgreSQL.

Key Components:
- KnowledgeGraphServer: Main MCP server implementation
- PostgresDB: Database connection and query execution
- ToolHandlers: Implementation of knowledge graph operations
- TOOL_DEFINITIONS: Available tool definitions

Example:
    from agent_kg import KnowledgeGraphServer
    server = KnowledgeGraphServer()
    asyncio.run(server.run())
"""

from .server import KnowledgeGraphServer
from .postgres import PostgresDB
from .handlers import ToolHandlers
from .tool_definitions import TOOL_DEFINITIONS

# Package metadata
__version__ = "0.1.0"
__author__ = "Agent KG Team"
__description__ = "Knowledge Graph MCP Server for Agent Memory Management"

# Expose key components at package level
__all__ = [
    "KnowledgeGraphServer",
    "PostgresDB",
    "ToolHandlers",
    "TOOL_DEFINITIONS",
    "__version__",
    "__author__",
    "__description__"
]
