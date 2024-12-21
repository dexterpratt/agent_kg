import logging
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl
from typing import Any
from snowflake.snowpark import Session
import os
import dotenv

logging.basicConfig(
    level=logging.INFO,  # Set the log level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # logging.FileHandler("logs/mcp_snowflake_server.log"),  # Log file path
        logging.StreamHandler(),  # Optional: still output to the console
    ],
)

logger = logging.getLogger("mcp_snowflake_server")
logger.info("Starting MCP Snowflake Server")


class SnowflakeDB:
    def __init__(self, connection_config: dict):
        self.connection_config = connection_config
        self._init_database()
        self.insights: list[str] = []

    def _init_database(self):
        """Initialize connection to the Snowflake database"""
        logger.debug("Initializing database connection")
        self.session = Session.builder.configs(self.connection_config).getOrCreate()
        self.session.sql("USE DATABASE " + self.connection_config.get("database").upper())
        self.session.sql("USE SCHEMA " + self.connection_config.get("schema").upper())
        self.session.sql("USE WAREHOUSE " + self.connection_config.get("warehouse").upper())

    def _synthesize_memo(self) -> str:
        """Synthesizes data insights into a formatted memo"""
        logger.debug(f"Synthesizing memo with {len(self.insights)} insights")
        if not self.insights:
            return "No data insights have been discovered yet."

        insights = "\n".join(f"- {insight}" for insight in self.insights)

        memo = "📊 Data Intelligence Memo 📊\n\n"
        memo += "Key Insights Discovered:\n\n"
        memo += insights

        if len(self.insights) > 1:
            memo += "\nSummary:\n"
            memo += f"Analysis has revealed {len(self.insights)} key data insights that suggest opportunities for strategic optimization and growth."

        logger.debug("Generated basic memo format")
        return memo

    def _execute_query(self, query: str) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries"""
        logger.debug(f"Executing query: {query}")
        try:
            result = self.session.sql(query).to_pandas()
            result_rows = result.to_dict(orient="records")
            single_line_query = query.replace("\n", " ")
            logger.debug(f"Query {single_line_query} returned {len(result_rows)} rows")
            return result_rows
        except Exception as e:
            logger.error(f'Database error executing "{query}": {e}')
            raise


async def main(allow_write: bool = False):
    logger.info("Starting Snowflake MCP Server")

    if not all(
        [
            os.getenv("SNOWFLAKE_ACCOUNT"),
            os.getenv("SNOWFLAKE_USER"),
            os.getenv("SNOWFLAKE_PASSWORD"),
            os.getenv("SNOWFLAKE_ROLE"),
            os.getenv("SNOWFLAKE_WAREHOUSE"),
            os.getenv("SNOWFLAKE_DATABASE"),
            os.getenv("SNOWFLAKE_SCHEMA"),
        ]
    ):
        dotenv.load_dotenv()
    connection_config = {
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "user": os.getenv("SNOWFLAKE_USER"),
        "password": os.getenv("SNOWFLAKE_PASSWORD"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    }
    db = SnowflakeDB(connection_config)
    server = Server("snowflake-manager")

    # Register handlers
    logger.debug("Registering handlers")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        logger.debug("Handling list_resources request")
        return [
            types.Resource(
                uri=AnyUrl("memo://insights"),
                name="Data Insights Memo",
                description="A living document of discovered data insights",
                mimeType="text/plain",
            )
        ]

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        logger.debug(f"Handling read_resource request for URI: {uri}")
        if uri.scheme != "memo":
            logger.error(f"Unsupported URI scheme: {uri.scheme}")
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        path = str(uri).replace("memo://", "")
        if not path or path != "insights":
            logger.error(f"Unknown resource path: {path}")
            raise ValueError(f"Unknown resource path: {path}")

        return db._synthesize_memo()

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        logger.debug("Handling list_prompts request")
        return []

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        logger.debug(f"Handling get_prompt request for {name} with args {arguments}")
        raise ValueError(f"Unknown prompt: {name}")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        write_tools = [
            types.Tool(
                name="write_query",
                description="Execute an INSERT, UPDATE, or DELETE query on the Snowflake database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query to execute"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="create_table",
                description="Create a new table in the Snowflake database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "CREATE TABLE SQL statement"},
                    },
                    "required": ["query"],
                },
            ),
        ]
        return [
            types.Tool(
                name="read_query",
                description="Execute a SELECT query on the Snowflake database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SELECT SQL query to execute"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="list_tables",
                description="List all tables in the Snowflake database",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="describe_table",
                description="Get the schema information for a specific table",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string", "description": "Name of the table to describe"},
                    },
                    "required": ["table_name"],
                },
            ),
            types.Tool(
                name="append_insight",
                description="Add a data insight to the memo",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "insight": {"type": "string", "description": "Data insight discovered from analysis"},
                    },
                    "required": ["insight"],
                },
            ),
        ] + (write_tools if allow_write else [])

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool execution requests"""
        logger.info(f"Handling tool execution request for {name} with args {arguments}")
        try:
            if name == "list_tables":
                logger.info("Listing tables")
                results = db._execute_query(
                    f"select table_catalog, table_schema, table_name, comment from insight_db.information_schema.tables where table_schema = '{connection_config.get('schema').upper()}'"
                )
                logger.info("Received results")
                return [types.TextContent(type="text", text=str(results), artifact={"type": "dataframe", "data": results})]

            elif name == "describe_table":
                if not arguments or "table_name" not in arguments:
                    raise ValueError("Missing table_name argument")

                split_identifier = arguments["table_name"].split(".")
                table_name = split_identifier[-1].upper()
                schema_name = (split_identifier[-2] if len(split_identifier) > 1 else connection_config.get("schema")).upper()
                database_name = (
                    split_identifier[-3] if len(split_identifier) > 2 else connection_config.get("database")
                ).upper()
                results = db._execute_query(
                    f"select column_name, column_default, is_nullable, data_type, comment from {database_name}.information_schema.columns where table_schema = '{schema_name}' and table_name = '{table_name}'"
                )
                return [types.TextContent(type="text", text=str(results), artifact={"type": "dataframe", "data": results})]
            elif name == "read_query":
                if not arguments["query"].strip().upper().startswith("SELECT"):
                    raise ValueError("Only SELECT queries are allowed for read_query")
                results = db._execute_query(arguments["query"])
                results_text = (
                    str(results)
                    if len(results) < 50
                    else str(results[:50])
                    + "\nResults of query have been truncated. There are "
                    + str(len(results) - 50)
                    + " more rows."
                )
                return [types.TextContent(type="text", text=results_text, artifact={"type": "dataframe", "data": results})]
            elif name == "append_insight":
                if not arguments or "insight" not in arguments:
                    raise ValueError("Missing insight argument")

                db.insights.append(arguments["insight"])
                _ = db._synthesize_memo()

                # Notify clients that the memo resource has changed
                await server.request_context.session.send_resource_updated(AnyUrl("memo://insights"))

                return [types.TextContent(type="text", text="Insight added to memo")]
            elif name == "write_query":
                if not allow_write:
                    raise ValueError("Write operations are not allowed for this data connection")
                if arguments["query"].strip().upper().startswith("SELECT"):
                    raise ValueError("SELECT queries are not allowed for write_query")
                results = db._execute_query(arguments["query"])
                return [types.TextContent(type="text", text=str(results))]

            elif name == "create_table":
                if not allow_write:
                    raise ValueError("Write operations are not allowed for this data connection")
                if not arguments["query"].strip().upper().startswith("CREATE TABLE"):
                    raise ValueError("Only CREATE TABLE statements are allowed")
                db._execute_query(arguments["query"])
                return [types.TextContent(type="text", text="Table created successfully")]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="snowflake",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
