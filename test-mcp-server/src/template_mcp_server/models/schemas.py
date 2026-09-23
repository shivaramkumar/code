"""Pydantic data models and schemas for template MCP server."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    GENERATE = "GENERATE"
    MIGRATE = "MIGRATE"
    ROLLBACK = "ROLLBACK"


class TemplateParameter(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Optional[Any] = None


class TemplateMetadata(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    file_type: str = "text"  # yaml, json, python, markdown, etc.
    default_filename: str = "output.txt"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    raw_template: Optional[str] = None
    submodule_commit: Optional[str] = None


class ComparisonResult(BaseModel):
    identical: bool
    drift_detected: bool
    added_fields: Dict[str, Any] = Field(default_factory=dict)
    removed_fields: Dict[str, Any] = Field(default_factory=dict)
    modified_fields: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    retained_fields: Dict[str, Any] = Field(default_factory=dict)
    help_text_drift: Optional[Dict[str, Any]] = None
    unified_diff: str = ""
    summary: str = ""


class MigrationResult(BaseModel):
    success: bool
    file_path: str
    template_name: str
    retained_fields: Dict[str, Any] = Field(default_factory=dict)
    retained_help_texts: Dict[str, Any] = Field(default_factory=dict)
    new_fields_applied: Dict[str, Any] = Field(default_factory=dict)
    diff: str = ""
    audit_id: Optional[str] = None
    dry_run: bool = False
    message: str = ""
    new_content: Optional[str] = None


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    action: AuditAction
    file_path: str
    template_name: Optional[str] = None
    git_commit: Optional[str] = None
    git_remote: Optional[str] = None
    previous_hash: Optional[str] = None
    new_hash: Optional[str] = None
    diff: str = ""
    snapshot_path: Optional[str] = None
    retained_fields: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
