"""Knowledge Graph MCP Server Package.

This package provides a FastMCP server implementation for managing a 
knowledge graph with support for entities stored in PostgreSQL.

Key Components:
- PostgresDB: Database connection and query execution
- FastMCP server: Direct implementation of MCP tools
"""

# Package metadata
__version__ = "0.1.0"
__author__ = "Agent KG Team"
__description__ = "Knowledge Graph FastMCP Server for Agent Memory Management"

# Expose key components at package level
__all__ = [
    "__version__",
    "__author__",
    "__description__"
]
