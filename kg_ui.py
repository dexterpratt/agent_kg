# kg_ui.py
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import os
import json
from mcp_client import MCPClient

# Global MCP client
mcp_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global mcp_client
    mcp_client = MCPClient()
    await mcp_client.connect_to_server("kg_access.py")
    
    yield
    
    # Shutdown
    if mcp_client:
        await mcp_client.cleanup()

app = FastAPI(lifespan=lifespan)

# Create static files directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class QueryRequest(BaseModel):
    sql: str

class EntityRequest(BaseModel):
    id: int

@app.post("/api/query")
async def execute_query(query: QueryRequest):
    try:
        result = await mcp_client.call_tool(
            "query_knowledge_graph_database",
            {"sql": query.sql}
        )
        # Parse the JSON string from MCP response and return the parsed object
        return json.loads(result.content[0].text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/entity/{entity_id}/properties")
async def get_entity_properties(entity_id: int):
    try:
        result = await mcp_client.call_tool(
            "get_properties",
            {"entity_id": entity_id}
        )
        return result.content[0].text
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8055)