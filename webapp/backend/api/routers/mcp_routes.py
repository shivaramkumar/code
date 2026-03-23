import asyncio
import json
from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse
from db.cache import context_collection

router = APIRouter()

# Keep track of active MCP clients
clients = set()

async def mcp_event_generator(request: Request):
    q = asyncio.Queue()
    clients.add(q)
    try:
        # Initial MCP Handshake
        yield {
            "event": "message",
            "data": json.dumps({"jsonrpc": "2.0", "result": {"capabilities": {"logging": {}, "resources": {}, "tools": {}}}, "id": "init"})
        }
        while True:
            if await request.is_disconnected():
                break
            message = await q.get()
            yield {"event": "message", "data": json.dumps(message)}
    finally:
        clients.remove(q)

@router.get("/sse")
async def mcp_sse(request: Request):
    """MCP Server-Sent Events Endpoint"""
    return EventSourceResponse(mcp_event_generator(request))

@router.post("/messages")
async def mcp_messages(request: Request):
    """Receive JSON-RPC messages from the MCP Client"""
    data = await request.json()
    method = data.get("method")
    
    response_data = None
    
    if method == "tools/list":
        # We can expose AI tasks or context retrieval as an MCP tool
        response_data = {
            "jsonrpc": "2.0",
            "id": data.get("id"),
            "result": {
                "tools": [{
                    "name": "retrieve_context",
                    "description": "Retrieve uploaded semantic context to answer user queries",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The concept to search for"}
                        },
                        "required": ["query"]
                    }
                }]
            }
        }
    elif method == "tools/call":
        tool_name = data.get("params", {}).get("name")
        params = data.get("params", {}).get("arguments", {})
        
        if tool_name == "retrieve_context":
            query = params.get("query", "")
            res = context_collection.query(query_texts=[query], n_results=2)
            docs = res.get("documents", [[]])[0]
            
            response_data = {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {
                    "content": [{"type": "text", "text": "\n".join(docs)}]
                }
            }
    
    if response_data:
         # Broadcast or respond directly
         for q in clients:
              await q.put(response_data)
         return {"status": "accepted"}
    
    return {"status": "unsupported method"}
