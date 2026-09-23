"""Template generator for rendering Jinja2 templates and writing files to workspace."""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import jinja2

from ..models.schemas import AuditAction
from .audit import AuditManager
from ..templates.registry import TemplateRegistry


class TemplateGenerator:
    """Renders Jinja2 templates and writes generated files to client workspace with audit tracking."""

    def __init__(self, registry: TemplateRegistry, audit_manager: Optional[AuditManager] = None):
        self.registry = registry
        self.audit_manager = audit_manager or AuditManager()

    def render(self, template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Render a template with provided context, falling back to schema defaults."""
        source = self.registry.get_template_source(template_name)
        if not source:
            raise ValueError(f"Template '{template_name}' not found.")

        defaults = self.registry.get_defaults(template_name)
        merged_context = {**defaults, **(context or {})}

        template = self.registry.jinja_env.from_string(source)
        return template.render(**merged_context)

    def generate_resource(
        self,
        template_name: str,
        target_path: str,
        context: Optional[Dict[str, Any]] = None,
        record_audit: bool = True,
        current_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Render template content without directly writing to a path."""
        rendered_content = self.render(template_name, context)
        path = Path(target_path)
        previous_content: Optional[str] = current_content
        if previous_content is None and path.exists():
            try:
                previous_content = path.read_text(encoding="utf-8")
            except Exception:
                pass

        audit_id: Optional[str] = None
        audit_bundle: Optional[Dict[str, Any]] = None
        if record_audit:
            sub_info = self.registry.get_submodule_info()
            audit_bundle = self.audit_manager.create_audit_bundle(
                action=AuditAction.GENERATE,
                file_path=str(path),
                previous_content=previous_content,
                new_content=rendered_content,
                template_name=template_name,
                git_commit=sub_info.get("commit_hash"),
                git_remote=sub_info.get("remote_url"),
                metadata={
                    "context_keys": list(context.keys()) if context else [],
                    "delivery": "embedded_resource",
                },
            )
            audit_id = audit_bundle["audit_id"]

        return {
            "path": target_path,
            "text": rendered_content,
            "audit_id": audit_id,
            "audit_bundle": audit_bundle,
            "previous_content": previous_content,
        }

    def generate_file(
        self,
        template_name: str,
        target_path: str,
        context: Optional[Dict[str, Any]] = None,
        overwrite: bool = False,
        current_content: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Render template and write to target path in client workspace."""
        path = Path(target_path)
        previous_content: Optional[str] = current_content

        if previous_content is None and path.exists():
            if not overwrite:
                return (
                    False,
                    f"File '{target_path}' already exists and overwrite is set to False.",
                    None,
                )
            previous_content = path.read_text(encoding="utf-8")
        elif previous_content is not None and not overwrite and path.exists():
            return (
                False,
                f"File '{target_path}' already exists and overwrite is set to False.",
                None,
            )

        rendered_content = self.render(template_name, context)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered_content, encoding="utf-8")

        sub_info = self.registry.get_submodule_info()
        audit_entry = self.audit_manager.record_action(
            action=AuditAction.GENERATE,
            file_path=str(path),
            previous_content=previous_content,
            new_content=rendered_content,
            template_name=template_name,
            git_commit=sub_info.get("commit_hash"),
            git_remote=sub_info.get("remote_url"),
            metadata={"context_keys": list(context.keys()) if context else []},
        )

        action_word = "overwritten" if previous_content is not None else "created"
        return (
            True,
            f"File '{target_path}' successfully {action_word} using template '{template_name}'. (Audit ID: {audit_entry.id})",
            audit_entry.id,
        )
