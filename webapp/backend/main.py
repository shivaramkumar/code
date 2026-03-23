from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import azure.functions as func

from api.routers import context, mcp_routes, ai, config, tools
import json
import os

app = FastAPI(
    title="LearnSpace Template",
    description="Educational Backend for semantic caching, context upload and MCP server.",
    version="1.0.0"
)

from db.models import SessionLocal, MCPTool

@app.on_event("startup")
def bootstrap_config_tools():
    config_path = os.path.join(os.path.dirname(__file__), "../config.json")
    try:
        with open(config_path, "r") as f:
            c = json.load(f)
            tools_list = c.get("mcp_tools", [])
            
            db = SessionLocal()
            for t in tools_list:
                existing = db.query(MCPTool).filter(MCPTool.name == t.get("name")).first()
                if not existing:
                    db_tool = MCPTool(
                        name=t.get("name"),
                        description=t.get("description", ""),
                        api_endpoint=t.get("api_endpoint"),
                        is_active=1
                    )
                    db.add(db_tool)
            db.commit()
            db.close()
    except Exception as e:
        print("Failed to sync config.json tools on startup:", e)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(config.router, prefix="/api/config", tags=["Configuration"])
app.include_router(tools.router, prefix="/api/tools", tags=["Tools"])
app.include_router(context.router, prefix="/api/context", tags=["Context"])
app.include_router(mcp_routes.router, prefix="/mcp", tags=["MCP"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])

# Mount frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

# Wrapper for Azure Functions
# function_app = func.AsgiFunctionApp(app=app, http_auth_level=func.AuthLevel.ANONYMOUS)
