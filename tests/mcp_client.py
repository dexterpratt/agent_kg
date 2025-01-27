

from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import os

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.available_tools = None

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = "python" if is_python else "node"
        
        env = {
            "PATH": os.environ["PATH"],  # Essential for finding executables
            "LOGLEVEL": "WARNING"        # Our desired logging control
        }

        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=env
)
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # Store available tools during connection
        response = await self.session.list_tools()
        self.available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]
        print("\nConnected to server with tools:", [tool["name"] for tool in self.available_tools])

    async def get_available_tools(self):
        """Return cached tools list or fetch if not yet cached"""
        if self.available_tools is None:
            response = await self.session.list_tools()
            self.available_tools = [{ 
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in response.tools]
        return self.available_tools
    
    async def call_tool(self, tool_name: str, tool_args: dict):
        # Execute tool call with proper arguments parameter
        result = await self.session.call_tool(tool_name, arguments=tool_args)
        return result
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()



