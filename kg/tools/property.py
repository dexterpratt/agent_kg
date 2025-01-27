# kg/tools/property.py
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("kg_access.property")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def register_property_tools(mcp, db):
    """Register property-related tools with the MCP server."""
    
    @mcp.tool()
    async def get_properties(entity_id: Optional[int] = None, 
                           relationship_id: Optional[int] = None,
                           key: Optional[str] = None) -> str:
        """Get properties for an entity or relationship."""
        try:
            if entity_id is None and relationship_id is None:
                raise ValueError("Must provide either entity_id or relationship_id")
                
            conditions = []
            params = []
            
            if entity_id is not None:
                conditions.append("entity_id = %s")
                params.append(entity_id)
            if relationship_id is not None:
                conditions.append("relationship_id = %s")
                params.append(relationship_id)
            if key is not None:
                conditions.append("key = %s")
                params.append(key)
                
            where_clause = " AND ".join(conditions)
            
            query = f"""
                SELECT id, entity_id, relationship_id, key, value, value_type
                FROM properties
                WHERE {where_clause}
            """
            
            results = db.execute_query(query, tuple(params))
            return json.dumps({
                "success": True,
                "properties": results or []
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error getting properties: {e}")
            raise ValueError(str(e))

    @mcp.tool()
    async def update_properties(entity_id: Optional[int] = None,
                            relationship_id: Optional[int] = None,
                            properties: Dict[str, Any] = {}) -> str:
        """Update properties for an entity or relationship."""
        try:
            # Input validation
            if entity_id is None and relationship_id is None:
                raise ValueError("Must provide either entity_id or relationship_id")
            if not properties:
                raise ValueError("No properties provided for update")
                
            # Verify entity/relationship exists
            if entity_id:
                exists_query = "SELECT id FROM entities WHERE id = %s"
                exists_params = (entity_id,)
            else:
                exists_query = "SELECT id FROM relationships WHERE id = %s"
                exists_params = (relationship_id,)
                
            exists = db.execute_query(exists_query, exists_params)
            if not exists:
                raise ValueError(f"{'Entity' if entity_id else 'Relationship'} not found")
            
            updated_properties = []
            for key, value in properties.items():
                # Try to update existing property
                owner_column = 'entity_id' if entity_id else 'relationship_id'
                owner_id = entity_id if entity_id else relationship_id
                
                # Update if exists
                update_query = f"""
                    UPDATE properties 
                    SET value = %s, last_updated = CURRENT_TIMESTAMP
                    WHERE {owner_column} = %s AND key = %s
                    RETURNING id, key, value, value_type
                """
                update_params = (str(value), owner_id, key)
                logger.debug(f"Executing update with params: {update_params}")
                result = db.execute_query(update_query, update_params)
                
                if result:
                    updated_properties.extend(result)
                else:
                    # Property doesn't exist, create it
                    insert_query = f"""
                        INSERT INTO properties ({owner_column}, key, value, value_type)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, key, value, value_type
                    """
                    insert_params = (owner_id, key, str(value), 'STRING')
                    logger.debug(f"Executing insert with params: {insert_params}")
                    result = db.execute_query(insert_query, insert_params)
                    updated_properties.extend(result)
            
            return json.dumps({
                "success": True,
                "updated_properties": updated_properties
            }, cls=DateTimeEncoder)
            
        except Exception as e:
            logger.error(f"Error updating properties: {e}")
            raise ValueError(str(e))
            
    @mcp.tool()
    async def delete_properties(entity_id: Optional[int] = None,
                              relationship_id: Optional[int] = None,
                              keys: Optional[list] = None) -> str:
        """Delete properties for an entity or relationship."""
        try:
            if entity_id is None and relationship_id is None:
                raise ValueError("Must provide either entity_id or relationship_id")
                
            conditions = []
            params = []
            
            if entity_id is not None:
                conditions.append("entity_id = %s")
                params.append(entity_id)
            if relationship_id is not None:
                conditions.append("relationship_id = %s")
                params.append(relationship_id)
                
            if keys:
                placeholders = ','.join(['%s'] * len(keys))
                conditions.append(f"key IN ({placeholders})")
                params.extend(keys)
                
            where_clause = " AND ".join(conditions)
            
            # Get properties to be deleted
            select_query = f"""
                SELECT id, key, value
                FROM properties
                WHERE {where_clause}
            """
            to_delete = db.execute_query(select_query, tuple(params))
            
            # Delete properties
            delete_query = f"DELETE FROM properties WHERE {where_clause}"
            db.execute_query(delete_query, tuple(params))
            
            return json.dumps({
                "success": True,
                "deleted_properties": to_delete or []
            }, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error deleting properties: {e}")
            raise ValueError(str(e))