# kg/tools/relationship.py
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("kg_access.relationship")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def register_relationship_tools(mcp, db):
    """Register relationship-related tools with the MCP server."""
    
    @mcp.tool()
    async def add_relationship(source_id: int, target_id: int, type: str, properties: Dict[str, Any] = {}) -> str:
        """Add a new relationship between entities with optional properties."""
        try:
            # Verify both entities exist
            entities_query = """
                SELECT id FROM entities 
                WHERE id IN (%s, %s)
            """
            results = db.execute_query(entities_query, (source_id, target_id))
            if not results or len(results) != 2:
                raise ValueError("Both source and target entities must exist")
            
            # Create relationship
            query = """
                INSERT INTO relationships (source_id, target_id, type)
                VALUES (%s, %s, %s)
                RETURNING id, source_id, target_id, type, created_at, last_updated
            """
            result = db.execute_query(query, (source_id, target_id, type))
            if not result or len(result) != 1:
                raise RuntimeError("Failed to create relationship")
                
            relationship_id = result[0]['id']
            
            # Add properties if provided
            for key, value in properties.items():
                prop_query = """
                    INSERT INTO properties (relationship_id, key, value, value_type)
                    VALUES (%s, %s, %s, 'STRING')
                """
                db.execute_query(prop_query, (relationship_id, key, str(value)))
            
            return json.dumps(result[0], cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error adding relationship: {e}")
            raise ValueError(str(e))

    @mcp.tool()
    async def update_relationship(id: int, type: str) -> str:
        """Update a relationship's type."""
        try:
            query = """
                UPDATE relationships 
                SET type = %s, last_updated = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, source_id, target_id, type, created_at, last_updated
            """
            result = db.execute_query(query, (type, id))
            if not result:
                raise ValueError(f"No relationship found with id {id}")
                
            return json.dumps(result[0], cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error updating relationship: {e}")
            raise ValueError(str(e))

    @mcp.tool()
    async def get_relationships(source_id: Optional[int] = None, 
                              target_id: Optional[int] = None, 
                              type: Optional[str] = None) -> str:
        """Get relationships with optional filters."""
        try:
            conditions = []
            params = []
            
            if source_id is not None:
                conditions.append("source_id = %s")
                params.append(source_id)
            if target_id is not None:
                conditions.append("target_id = %s")
                params.append(target_id)
            if type is not None:
                conditions.append("type = %s")
                params.append(type)
                
            where_clause = " AND ".join(conditions) if conditions else "TRUE"
            
            query = f"""
                SELECT id, source_id, target_id, type, created_at, last_updated
                FROM relationships
                WHERE {where_clause}
            """
            
            results = db.execute_query(query, tuple(params))
            return json.dumps({
                "success": True,
                "relationships": results or []
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error getting relationships: {e}")
            raise ValueError(str(e))

    @mcp.tool()
    async def delete_relationship(id: int) -> str:
        """Delete a relationship and its properties."""
        try:
            # Delete properties first due to foreign key constraints
            db.execute_query("DELETE FROM properties WHERE relationship_id = %s", (id,))
            
            # Delete relationship
            db.execute_query("DELETE FROM relationships WHERE id = %s", (id,))
            
            return json.dumps({"success": True})
        except Exception as e:
            logger.error(f"Error deleting relationship: {e}")
            raise ValueError(str(e))