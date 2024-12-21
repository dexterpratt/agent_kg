"""Module containing tool definitions for the knowledge graph server."""

TOOL_DEFINITIONS = [
    {
        "name": "add_entity",
        "description": "Add a new entity to the knowledge graph",
        "inputSchema": {
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
    },
    {
        "name": "get_entity",
        "description": "Get an entity by ID or name",
        "inputSchema": {
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
    },
    {
        "name": "update_entity",
        "description": "Update an entity's properties",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "properties": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["id", "properties"]
        }
    },
    {
        "name": "delete_entity",
        "description": "Delete an entity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "add_relationship",
        "description": "Add a relationship between entities",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "integer"},
                "target_id": {"type": "integer"},
                "type": {"type": "string"},
                "properties": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["source_id", "target_id", "type"]
        }
    },
    {
        "name": "get_relationships",
        "description": "Get relationships for an entity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "direction": {
                    "type": "string",
                    "enum": ["incoming", "outgoing", "both"]
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "update_relationship",
        "description": "Update a relationship's properties",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "properties": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["id", "properties"]
        }
    },
    {
        "name": "delete_relationship",
        "description": "Delete a relationship",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "search_entities",
        "description": "Search entities by properties",
        "inputSchema": {
            "type": "object",
            "properties": {
                "properties": {
                    "type": "object",
                    "additionalProperties": True
                },
                "type": {"type": "string"}
            },
            "required": ["properties"]
        }
    },
    {
        "name": "get_connected_entities",
        "description": "Get entities connected to a given entity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "relationship_type": {"type": "string"}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "set_context",
        "description": "Set a context entry",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "key": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "get_context",
        "description": "Get context entries",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"}
            }
        }
    }
]
