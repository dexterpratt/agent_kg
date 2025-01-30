# kg/tools/entity.py
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("kg_access.entity")

def register_entity_tools(mcp, db):
    """Register entity-related tools with the MCP server."""
    
    @mcp.tool()
    async def add_entity(type: str, name: Optional[str] = None, properties: Dict[str, Any] = {}) -> str:
        """Add a new entity to the graph with optional properties. 
        It returns a json object with properties id, type, name, created_at, last_updated"""
        try:
            query = """
                INSERT INTO entities (type, name)
                VALUES (%s, %s)
                RETURNING id, type, name, created_at, last_updated
            """
            result = db.execute_query(query, (type, name))
            if not result or len(result) != 1:
                raise RuntimeError("Failed to create entity")
                
            entity_id = result[0]['id']
            
            # Add properties if provided
            for key, value in properties.items():
                prop_query = """
                    INSERT INTO properties (entity_id, key, value, value_type)
                    VALUES (%s, %s, %s, 'STRING')
                """
                db.execute_query(prop_query, (entity_id, key, str(value)))
            
            # Convert datetime objects to ISO format for JSON serialization
            result[0]['created_at'] = result[0]['created_at'].isoformat()
            result[0]['last_updated'] = result[0]['last_updated'].isoformat()
                
            return json.dumps(result[0])
        except Exception as e:
            logger.error(f"Error adding entity: {e}")
            raise ValueError(str(e))

    @mcp.tool()
    async def delete_entity(id: int) -> str:
        """Delete an entity and all its properties. 
        It returns {"success": True} if successful"""
        try:
            # Delete properties first
            db.execute_query("DELETE FROM properties WHERE entity_id = %s", (id,))
            
            # Delete entity
            db.execute_query("DELETE FROM entities WHERE id = %s", (id,))
            
            return json.dumps({"success": True})
        except Exception as e:
            logger.error(f"Error deleting entity: {e}")
            raise ValueError(str(e))