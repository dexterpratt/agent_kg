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
import json
from datetime import datetime


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

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)
        
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
        
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=name,
                    description=desc,
                    inputSchema=schema
                ) for name, desc, schema in TOOL_DEFINITIONS
            ]

        async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
            handler = getattr(self.handlers, name, None)
            if not handler:
                raise ValueError(f"Unknown tool: {name}")
            
            try:
                result = await handler(arguments or {})
                # Convert the result to proper JSON format with custom encoder
                result_json = json.dumps(result, cls=CustomJSONEncoder)
                return [types.TextContent(type="text", text=result_json)]
            except Exception as e:
                raise ValueError(f"Tool execution failed: {str(e)}")

        # Set the handlers directly
        self.server.handle_list_tools = handle_list_tools
        self.server.handle_call_tool = handle_call_tool

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