"""MCP server implementation for the knowledge graph."""

import asyncio
import logging
import os
import sys
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl
from typing import Any
from .postgres import PostgresDB
from .tool_definitions import TOOL_DEFINITIONS
from .handlers import ToolHandlers
import dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("knowledge_graph_server")
logger.info("Initializing Knowledge Graph MCP Server")

# Load environment variables
dotenv.load_dotenv()

class KnowledgeGraphServer:
    def __init__(self):
        # Initialize MCP server
        self.server = Server("agent-kg")

        # Initialize database connection
        connection_config = {
            "dbname": os.getenv("POSTGRES_DB", "memento"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": os.getenv("POSTGRES_PORT", "5432"),
        }
        self.db = PostgresDB(connection_config)
        
        # Initialize tool handlers
        self.handlers = ToolHandlers(self.db)
        
        # Set up request handlers
        self.setup_tool_handlers()
        
        # Error handling
        self.server.onerror = lambda error: logger.error(f"[MCP Error] {error}")

    def setup_tool_handlers(self) -> None:
        """Configure the available tools"""
        
        @self.server.list_tools
        async def handle_list_tools() -> list[types.Tool]:
            """Return list of available tools"""
            return [
                types.Tool(
                    name="add_entity",
                    description="Add a new entity to the graph",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "name": {"type": "string"},
                            "properties": {
                                "type": "object",
                                "additionalProperties": True
                            }
                        },
                        "required": ["type", "name"]
                    }
                ),
                # Add other tools with their schemas
                types.Tool(
                    name="get_entity",
                    description="Get an entity by ID or name",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"}
                        },
                        "oneOf": [
                            {"required": ["id"]},
                            {"required": ["name"]}
                        ]
                    }
                ),
                # ... Add the rest of the tools
            ]

    @self.server.call_tool
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        """Handle tool calls by dispatching to appropriate handler"""
        handler = getattr(self.handlers, name, None)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        
        try:
            result = await handler(arguments or {})
            return [types.TextContent(type="text", text=str(result))]
        except Exception as e:
            raise ValueError(f"Tool execution failed: {str(e)}")

    async def run(self) -> None:
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("Knowledge Graph MCP server running on stdio")
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="agent-kg",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    async def cleanup(self) -> None:
        """Clean up server resources."""
        try:
            if hasattr(self, 'db'):
                self.db.close()
            logger.info("Server resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during server cleanup: {e}")
            raise

def main() -> None:
    """Entry point for the MCP server"""
    server = KnowledgeGraphServer()
    try:
        asyncio.run(server.run())
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)
    finally:
        asyncio.run(server.cleanup())

if __name__ == "__main__":
    main()