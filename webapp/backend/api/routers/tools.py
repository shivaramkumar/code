from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from db.models import get_db, MCPTool

router = APIRouter()

class ToolCreate(BaseModel):
    name: str
    description: str
    api_endpoint: Optional[str] = None

class ToolResponse(BaseModel):
    id: int
    name: str
    description: str
    api_endpoint: Optional[str] = None
    is_active: int

    class Config:
        orm_mode = True

@router.get("", response_model=List[ToolResponse])
def get_tools(db: Session = Depends(get_db)):
    """Fetch all registered MCP Tools from the dynamic repository."""
    return db.query(MCPTool).all()

@router.post("", response_model=ToolResponse)
def register_tool(tool: ToolCreate, db: Session = Depends(get_db)):
    """Dynamically register a new MCP context tool."""
    existing = db.query(MCPTool).filter(MCPTool.name == tool.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tool name already registered.")
        
    db_tool = MCPTool(
        name=tool.name,
        description=tool.description,
        api_endpoint=tool.api_endpoint,
        is_active=1
    )
    db.add(db_tool)
    db.commit()
    db.refresh(db_tool)
    return db_tool

@router.delete("/{tool_id}")
def delete_tool(tool_id: int, db: Session = Depends(get_db)):
    tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    db.delete(tool)
    db.commit()
    return {"status": "deleted"}
