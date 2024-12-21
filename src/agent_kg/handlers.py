"""Module containing tool handlers for the knowledge graph server."""

from typing import Dict, Any


class ToolHandlers:
    def __init__(self, db):
        self.db = db

    async def add_entity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new entity to the graph"""
        query = """
        INSERT INTO entities (type, name) 
        VALUES (%s, %s) 
        RETURNING id
        """
        result = self.db.execute_query(query, (args["type"], args["name"]))
        entity_id = result[0]["id"]

        if "properties" in args and args["properties"]:
            for key, value in args["properties"].items():
                query = """
                INSERT INTO properties (entity_id, key, value, value_type) 
                VALUES (%s, %s, %s, %s)
                """
                value_type = type(value).__name__
                self.db.execute_query(query, (entity_id, key, str(value), value_type))

        return {"id": entity_id}

    async def get_entity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get an entity by ID or name"""
        if "id" in args:
            query = """
            SELECT e.*, json_object_agg(p.key, p.value) as properties
            FROM entities e
            LEFT JOIN properties p ON e.id = p.entity_id
            WHERE e.id = %s
            GROUP BY e.id
            """
            params = (args["id"],)
        else:
            query = """
            SELECT e.*, json_object_agg(p.key, p.value) as properties
            FROM entities e
            LEFT JOIN properties p ON e.id = p.entity_id
            WHERE e.name = %s
            GROUP BY e.id
            """
            params = (args["name"],)

        result = self.db.execute_query(query, params)
        if not result:
            raise ValueError(f"Entity not found with {'id' if 'id' in args else 'name'}: {args.get('id', args.get('name'))}")
        return result[0]

    async def update_entity(self, args: Dict[str, Any]) -> Dict[str, bool]:
        """Update an entity's properties"""
        entity_id = args["id"]
        properties = args["properties"]

        # Delete existing properties
        query = "DELETE FROM properties WHERE entity_id = %s"
        self.db.execute_query(query, (entity_id,))

        # Add new properties
        for key, value in properties.items():
            query = """
            INSERT INTO properties (entity_id, key, value, value_type) 
            VALUES (%s, %s, %s, %s)
            """
            value_type = type(value).__name__
            self.db.execute_query(query, (entity_id, key, str(value), value_type))

        return {"success": True}

    async def delete_entity(self, args: Dict[str, Any]) -> Dict[str, bool]:
        """Delete an entity"""
        # Delete associated properties first
        query = "DELETE FROM properties WHERE entity_id = %s"
        self.db.execute_query(query, (args["id"],))

        # Delete the entity
        query = "DELETE FROM entities WHERE id = %s"
        self.db.execute_query(query, (args["id"],))

        return {"success": True}

    async def add_relationship(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a relationship between entities"""
        query = """
        INSERT INTO relationships (source_id, target_id, type) 
        VALUES (%s, %s, %s) 
        RETURNING id
        """
        result = self.db.execute_query(
            query, (args["source_id"], args["target_id"], args["type"])
        )
        relationship_id = result[0]["id"]

        if "properties" in args and args["properties"]:
            for key, value in args["properties"].items():
                query = """
                INSERT INTO properties (relationship_id, key, value, value_type) 
                VALUES (%s, %s, %s, %s)
                """
                value_type = type(value).__name__
                self.db.execute_query(query, (relationship_id, key, str(value), value_type))

        return {"id": relationship_id}

    async def get_relationships(self, args: Dict[str, Any]) -> list:
        """Get relationships for an entity"""
        direction = args.get("direction", "both")
        
        if direction == "outgoing":
            query = """
            SELECT r.*, json_object_agg(p.key, p.value) as properties
            FROM relationships r
            LEFT JOIN properties p ON r.id = p.relationship_id
            WHERE r.source_id = %s
            GROUP BY r.id
            """
            params = (args["entity_id"],)
        elif direction == "incoming":
            query = """
            SELECT r.*, json_object_agg(p.key, p.value) as properties
            FROM relationships r
            LEFT JOIN properties p ON r.id = p.relationship_id
            WHERE r.target_id = %s
            GROUP BY r.id
            """
            params = (args["entity_id"],)
        else:  # both
            query = """
            SELECT r.*, json_object_agg(p.key, p.value) as properties
            FROM relationships r
            LEFT JOIN properties p ON r.id = p.relationship_id
            WHERE r.source_id = %s OR r.target_id = %s
            GROUP BY r.id
            """
            params = (args["entity_id"], args["entity_id"])

        return self.db.execute_query(query, params)

    async def update_relationship(self, args: Dict[str, Any]) -> Dict[str, bool]:
        """Update a relationship's properties"""
        relationship_id = args["id"]
        properties = args["properties"]

        # Delete existing properties
        query = "DELETE FROM properties WHERE relationship_id = %s"
        self.db.execute_query(query, (relationship_id,))

        # Add new properties
        for key, value in properties.items():
            query = """
            INSERT INTO properties (relationship_id, key, value, value_type) 
            VALUES (%s, %s, %s, %s)
            """
            value_type = type(value).__name__
            self.db.execute_query(query, (relationship_id, key, str(value), value_type))

        return {"success": True}

    async def delete_relationship(self, args: Dict[str, Any]) -> Dict[str, bool]:
        """Delete a relationship"""
        # Delete associated properties first
        query = "DELETE FROM properties WHERE relationship_id = %s"
        self.db.execute_query(query, (args["id"],))

        # Delete the relationship
        query = "DELETE FROM relationships WHERE id = %s"
        self.db.execute_query(query, (args["id"],))

        return {"success": True}

    async def search_entities(self, args: Dict[str, Any]) -> list:
        """Search entities by properties"""
        conditions = []
        params = []
        
        # Handle property-based search conditions if present
        if "properties" in args:
            for key, value in args["properties"].items():
                conditions.append("EXISTS (SELECT 1 FROM properties WHERE entity_id = e.id AND key = %s AND value = %s)")
                params.extend([key, str(value)])

        # Handle type-based search if present
        if "type" in args:
            conditions.append("e.type = %s")
            params.append(args["type"])

        # If no conditions, return all entities
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
        SELECT e.*, json_object_agg(p.key, p.value) as properties
        FROM entities e
        LEFT JOIN properties p ON e.id = p.entity_id
        WHERE {where_clause}
        GROUP BY e.id
        """
        
        return self.db.execute_query(query, tuple(params))

    async def get_connected_entities(self, args: Dict[str, Any]) -> list:
        """Get entities connected to a given entity"""
        entity_id = args["entity_id"]
        relationship_type = args.get("relationship_type")

        params = [
            entity_id,  # For the first CASE expression
            entity_id,  # For the second CASE within JOIN
            entity_id,  # For first part of WHERE clause
            entity_id,  # For second part of WHERE clause
        ]
        
        type_condition = ""
        if relationship_type:
            type_condition = "AND r.type = %s"
            params.append(relationship_type)

        query = f"""
            SELECT e.*, json_object_agg(p.key, p.value) as properties,
                r.type as relationship_type,
                CASE WHEN r.source_id = %s THEN 'outgoing' ELSE 'incoming' END as direction
            FROM relationships r
            JOIN entities e ON (
                CASE 
                    WHEN r.source_id = %s THEN r.target_id = e.id
                    ELSE r.source_id = e.id
                END
            )
            LEFT JOIN properties p ON e.id = p.entity_id
            WHERE (r.source_id = %s OR r.target_id = %s)
            {type_condition}
            GROUP BY e.id, r.type, r.source_id
            """
        
        return self.db.execute_query(query, tuple(params))

    async def set_context(self, args: Dict[str, Any]) -> Dict[str, bool]:
        """Set a context entry"""
        # Ensure category exists
        query = """
        INSERT INTO context_categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        RETURNING id
        """
        result = self.db.execute_query(query, (args["category"],))
        
        if result:
            category_id = result[0]["id"]
        else:
            query = "SELECT id FROM context_categories WHERE name = %s"
            result = self.db.execute_query(query, (args["category"],))
            category_id = result[0]["id"]

        # Update or insert context entry
        query = """
        INSERT INTO context_entries (category_id, key, value)
        VALUES (%s, %s, %s)
        ON CONFLICT (category_id, key) 
        DO UPDATE SET value = EXCLUDED.value
        """
        self.db.execute_query(query, (category_id, args["key"], args["value"]))
        
        return {"success": True}

    async def get_context(self, args: Dict[str, Any]) -> list:
        """Get context entries"""
        if "category" in args:
            query = """
            SELECT c.name as category, e.key, e.value
            FROM context_entries e
            JOIN context_categories c ON e.category_id = c.id
            WHERE c.name = %s
            """
            return self.db.execute_query(query, (args["category"],))
        else:
            query = """
            SELECT c.name as category, e.key, e.value
            FROM context_entries e
            JOIN context_categories c ON e.category_id = c.id
            """
            return self.db.execute_query(query)
