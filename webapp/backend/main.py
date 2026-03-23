from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import azure.functions as func

from api.routers import context, mcp_routes, ai

app = FastAPI(
    title="Context & MCP AI WebApp",
    description="Backend for semantic caching, context upload and MCP server.",
    version="1.0.0"
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(context.router, prefix="/api/context", tags=["Context"])
app.include_router(mcp_routes.router, prefix="/mcp", tags=["MCP"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])

# Mount frontend
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

# Wrapper for Azure Functions
# function_app = func.AsgiFunctionApp(app=app, http_auth_level=func.AuthLevel.ANONYMOUS)
