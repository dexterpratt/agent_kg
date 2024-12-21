"""Definitions for the Knowledge Graph MCP server tools."""

from typing import List, Tuple, Dict, Any

# Each tuple contains (name, description, input_schema)
TOOL_DEFINITIONS: List[Tuple[str, str, Dict[str, Any]]] = [
    (
        "add_entity",
        "Add a new entity to the graph",
        {
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
    ),
    (
        "get_entity",
        "Get an entity by ID or name",
        {
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
    ),
    (
        "update_entity",
        "Update an entity's properties",
        {
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
    ),
    (
        "delete_entity",
        "Delete an entity",
        {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}
            },
            "required": ["id"]
        }
    ),
    (
        "add_relationship",
        "Add a relationship between entities",
        {
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
    ),
    (
        "get_relationships",
        "Get relationships for an entity",
        {
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
    ),
    (
        "update_relationship",
        "Update a relationship's properties",
        {
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
    ),
    (
        "delete_relationship",
        "Delete a relationship",
        {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}
            },
            "required": ["id"]
        }
    ),
    (
        "search_entities",
        "Search entities by type and/or properties",
        {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "properties": {
                    "type": "object",
                    "additionalProperties": True
                }
            }
        }
    ),
    (
        "get_connected_entities",
        "Get entities connected to a given entity",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "relationship_type": {"type": "string"}
            },
            "required": ["entity_id"]
        }
    ),
    (
        "set_context",
        "Set a context entry",
        {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "key": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["category", "key", "value"]
        }
    ),
    (
        "get_context",
        "Get context entries",
        {
            "type": "object",
            "properties": {
                "category": {"type": "string"}
            }
        }
    )
]