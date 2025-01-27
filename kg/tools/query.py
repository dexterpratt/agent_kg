# kg/tools/query.py
import json
import logging
from datetime import datetime

logger = logging.getLogger("kg_access.query")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def register_query_tools(mcp, db):
    """Register query-related tools with the MCP server."""
    
    @mcp.tool()
    async def query_knowledge_graph_database(sql: str) -> str:
        """Execute a SQL query against the knowledge graph database."""
        try:
            results = db.execute_query(sql)
            return json.dumps({
                "success": True,
                "results": results or []
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Query error: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            })