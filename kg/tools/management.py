# kg/tools/management.py
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("kg_access.management")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def register_management_tools(mcp, db):
    """Register database management tools with the MCP server."""
    
    @mcp.tool()
    async def list_tables() -> str:
        """Get a list of all tables in the knowledge graph database."""
        try:
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
            
            results = db.execute_query(query)
            return json.dumps({
                "success": True,
                "tables": [row['table_name'] for row in results] if results else []
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error listing tables: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            })

    @mcp.tool()
    async def describe_table(table_name: str) -> str:
        """Get detailed schema information for a specific table."""
        try:
            # Verify table exists
            verify_query = """
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                ) as exists
            """
            exists = db.execute_query(verify_query, (table_name,))
            if not exists or not exists[0]['exists']:
                raise ValueError(f"Table '{table_name}' does not exist")

            # Get column information
            columns_query = """
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    column_default,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position
            """
            
            # Get constraint information
            constraints_query = """
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_name as foreign_table_name,
                    ccu.column_name as foreign_column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = %s
            """
            
            columns = db.execute_query(columns_query, (table_name,))
            constraints = db.execute_query(constraints_query, (table_name,))
            
            return json.dumps({
                "success": True,
                "table_name": table_name,
                "columns": columns,
                "constraints": constraints
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error describing table: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            })