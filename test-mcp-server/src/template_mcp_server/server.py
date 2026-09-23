"""FastMCP Server exposing tools, resources, templates, and prompts."""

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union
import click

logger = logging.getLogger(__name__)
try:
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("template-migrator-server")
except ImportError:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("template-migrator-server")
from mcp.types import EmbeddedResource, TextResourceContents
# Ensure src directory is in sys.path when executed directly as a script
from pathlib import Path
_src_path = str(Path(__file__).resolve().parent.parent)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from template_mcp_server.engine.audit import AuditManager
from template_mcp_server.engine.comparator import FieldExtractor, TextComparator
from template_mcp_server.engine.generator import TemplateGenerator
from template_mcp_server.engine.migrator import TemplateMigrator
from template_mcp_server.models.schemas import AuditAction
from template_mcp_server.templates.registry import TemplateRegistry

# Initialize core services
registry = TemplateRegistry()
audit_manager = AuditManager()
generator = TemplateGenerator(registry, audit_manager)
comparator = TextComparator(registry)
migrator = TemplateMigrator(registry, generator, audit_manager)

# Register audit_manager as MCP server middleware
mcp.middleware.append(audit_manager)



# ==========================================
# MCP TOOLS
# ==========================================

@mcp.tool()
def list_templates() -> List[Dict[str, Any]]:
    """List all available Jinja2 templates, their descriptions, versions, and parameters."""
    templates = registry.list_templates()
    return [t.model_dump() for t in templates]


@mcp.tool()
def get_template_schema(template_name: str) -> Dict[str, Any]:
    """Retrieve schema, parameters, and metadata for a specific template.

    Args:
        template_name: Name of the template (e.g. 'config_yaml', 'python_service', 'docker_compose', 'markdown_doc').
    """
    meta = registry.get_template_metadata(template_name)
    if not meta:
        return {"error": f"Template '{template_name}' not found."}
    return meta.model_dump()


@mcp.tool()
def render_template(template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Render a Jinja2 template with context without modifying any files (dry run preview).

    Args:
        template_name: Name of the template to render.
        context: Key-value parameters matching template schema to fill into the template.
    """
    try:
        return generator.render(template_name, context)
    except Exception as e:
        return f"Error rendering template: {str(e)}"


def _get_mime_type(path_str: str) -> str:
    """Determine MIME type based on file path or extension."""
    import mimetypes
    mime, _ = mimetypes.guess_type(path_str)
    if mime:
        return mime
    ext = Path(path_str).suffix.lower()
    mapping = {
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".json": "application/json",
        ".py": "text/x-python",
        ".md": "text/markdown",
        ".toml": "application/toml",
        ".txt": "text/plain",
        ".sh": "text/x-shellscript",
        ".dockerfile": "text/x-dockerfile",
    }
    return mapping.get(ext, "text/plain")


@mcp.tool()
def generate_files(
    files: Optional[List[Dict[str, Any]]] = None,
    template_name: Optional[str] = None,
    target_path: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    current_content: Optional[str] = None,
    include_client_audit: bool = True,
) -> List[EmbeddedResource]:
    """Generate template file(s) and return them as EmbeddedResource objects.
    
    IMPORTANT INSTRUCTION FOR CALLING AGENT / TOOL:
    This MCP server runs as a template service and does NOT write files directly to your local disk.
    Upon receiving the EmbeddedResource list, the calling agent MUST immediately use its local client
    workspace toolbox (e.g. write_file, create_file, or edit_file) to write the returned 'text' content
    to the target path specified in each resource's 'uri' within the local client workspace.
    When client audit is enabled, write/append to '.mcp_audit/audit_log.jsonl' and snapshot files as well.
    
    Args:
        files: Optional list of file objects. Each object can contain:
               - 'template_name': name of the template to render
               - 'path' or 'target_path': destination path for the file URI
               - 'context': optional key-value dictionary for template variables
               - 'text': optional pre-rendered text (used directly if provided)
               - 'current_content': optional current content of the file from client workspace
        template_name: Optional single template name if generating one file directly.
        target_path: Optional single target path if generating one file directly.
        context: Optional template variables if generating one file directly.
        current_content: Optional current content of the target file in client workspace (for diff/snapshot).
        include_client_audit: If True (default), bundles client workspace audit log (.mcp_audit/audit_log.jsonl)
                              and rollback snapshot files as EmbeddedResource objects.

    Returns:
        A list of EmbeddedResource objects containing file URIs, MIME types, and rendered text.
    """
    file_specs: List[Dict[str, Any]] = []
    if files:
        file_specs.extend(files)
    if template_name and target_path:
        file_specs.append({
            "template_name": template_name,
            "path": target_path,
            "context": context or {},
            "current_content": current_content,
        })

    rendered_files: List[Dict[str, str]] = []
    client_audit_logs: Dict[str, List[str]] = {}
    snapshot_resources: List[Dict[str, str]] = []

    for f in file_specs:
        path = f.get("path") or f.get("target_path", "output.txt")
        curr_content = f.get("current_content") or f.get("previous_content")
        if curr_content is None and f.get("path") == target_path:
            curr_content = current_content

        if "text" in f:
            text = f["text"]
            t_name = f.get("template_name")
            if t_name and include_client_audit:
                bundle = audit_manager.create_audit_bundle(
                    action=AuditAction.GENERATE,
                    file_path=path,
                    previous_content=curr_content,
                    new_content=text,
                    template_name=t_name,
                )
                log_p = bundle["audit_log_path"]
                client_audit_logs.setdefault(log_p, []).append(bundle["audit_log_text"])
                if bundle.get("snapshot_path") and bundle.get("snapshot_text") is not None:
                    snapshot_resources.append({
                        "path": bundle["snapshot_path"],
                        "text": bundle["snapshot_text"],
                    })
        else:
            t_name = f.get("template_name")
            if not t_name:
                continue
            ctx = f.get("context", {})
            res = generator.generate_resource(
                template_name=t_name,
                target_path=path,
                context=ctx,
                current_content=curr_content,
                record_audit=True,
            )
            text = res["text"]
            bundle = res.get("audit_bundle")
            if bundle and include_client_audit:
                log_p = bundle["audit_log_path"]
                client_audit_logs.setdefault(log_p, []).append(bundle["audit_log_text"])
                if bundle.get("snapshot_path") and bundle.get("snapshot_text") is not None:
                    snapshot_resources.append({
                        "path": bundle["snapshot_path"],
                        "text": bundle["snapshot_text"],
                    })

        rendered_files.append({"path": path, "text": text})

    resources: List[EmbeddedResource] = []

    # 1. Target code / config files
    for f in rendered_files:
        resources.append(
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=f"file:///{f['path'].lstrip('/')}",
                    mimeType=_get_mime_type(f["path"]),
                    text=f["text"],
                ),
            )
        )

    # 2. Client audit log files (.mcp_audit/audit_log.jsonl)
    if include_client_audit:
        for audit_log_path, lines in client_audit_logs.items():
            resources.append(
                EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=f"file:///{audit_log_path.lstrip('/')}",
                        mimeType="application/x-ndjson",
                        text="".join(lines),
                    ),
                )
            )

        # 3. Client snapshot files (.mcp_audit/snapshots/...)
        for snap in snapshot_resources:
            resources.append(
                EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=f"file:///{snap['path'].lstrip('/')}",
                        mimeType="text/plain",
                        text=snap["text"],
                    ),
                )
            )

    return resources


@mcp.tool()
def generate_file(
    template_name: str,
    target_path: str,
    context: Optional[Dict[str, Any]] = None,
    current_content: Optional[str] = None,
    include_client_audit: bool = True,
) -> List[EmbeddedResource]:
    """Render a Jinja2 template and return it as an EmbeddedResource bundle.

    IMPORTANT INSTRUCTION FOR CALLING AGENT / TOOL:
    This MCP server runs as a template service and does NOT write files directly to your local disk.
    Upon receiving the EmbeddedResource list, the calling agent MUST immediately use its local client
    workspace toolbox (e.g. write_file, create_file, or edit_file) to write the returned 'text' content
    to 'target_path' in the local client workspace.
    When client audit is enabled, write/append to '.mcp_audit/audit_log.jsonl' and snapshot files as well.

    Args:
        template_name: Name of the template to use.
        target_path: Destination file path in client workspace.
        context: Values to populate the template.
        current_content: Optional current content of the file from client workspace.
        include_client_audit: If True (default), bundles client audit log and snapshot resources.

    Returns:
        A list of EmbeddedResource objects containing file URIs, MIME types, and rendered text.
    """
    return generate_files(
        template_name=template_name,
        target_path=target_path,
        context=context,
        current_content=current_content,
        include_client_audit=include_client_audit,
    )


@mcp.tool()
def extract_fields(content: str, file_type: str = "auto") -> Dict[str, Any]:
    """Extract structured model fields from arbitrary text or file content.

    Args:
        content: Raw text content from workspace file.
        file_type: Format hint ('auto', 'yaml', 'json', 'python', 'markdown', 'key_value').
    """
    return FieldExtractor.extract(content, file_type)


@mcp.tool()
def compare_text(
    template_name: str,
    current_text: str,
    model_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare client workspace text against a server template/model to identify drift and structural differences.

    Args:
        template_name: The server template to compare against.
        current_text: Current file content from the client workspace.
        model_data: Optional custom model data; if omitted, template defaults are used.
    """
    try:
        result = comparator.compare_with_template(
            template_name=template_name,
            current_text=current_text,
            model_data=model_data,
        )
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def compare_workspace_file(
    file_path: str,
    template_name: str,
    model_data: Optional[Dict[str, Any]] = None,
    current_content: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare an existing client workspace file against a server template to identify differences and field drift.

    Args:
        file_path: Path to the existing file in the client workspace (used for diff reporting).
        template_name: Template name to compare against.
        model_data: Optional model parameters.
        current_content: Optional current content of the file from client workspace.
                         In a distributed client-server setup, the calling agent should read the file
                         locally using its client toolbox and pass its content here so no server-side disk access is needed.
    """
    try:
        result = comparator.compare_file(
            file_path=file_path,
            template_name=template_name,
            model_data=model_data,
            current_content=current_content,
        )
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def migrate_file(
    file_path: str,
    template_name: str,
    extra_updates: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    current_content: Optional[str] = None,
    return_resources: bool = False,
) -> Union[Dict[str, Any], List[EmbeddedResource]]:
    """Migrate a client workspace file to the latest template version while strictly retaining existing user field values.

    Args:
        file_path: Path to the client workspace file to update.
        template_name: Target template name to upgrade to.
        extra_updates: Optional new or updated parameters to apply during migration.
        dry_run: If True, returns diff and field mapping without modifying files or recording changes.
        current_content: Optional current content of the file from client workspace.
                         In a distributed client-server setup, the calling agent should read the file
                         locally using its client toolbox and pass its content here so no server-side disk access is needed.
        return_resources: If True, returns a List[EmbeddedResource] bundle containing the migrated file,
                          the client audit log entry, and rollback snapshot for local client workspace writing.
    """
    result = migrator.migrate_file(
        file_path=file_path,
        template_name=template_name,
        extra_updates=extra_updates,
        dry_run=dry_run,
        current_content=current_content,
    )

    if return_resources and result.success and result.new_content:
        bundle = audit_manager.create_audit_bundle(
            action=AuditAction.MIGRATE,
            file_path=file_path,
            previous_content=current_content,
            new_content=result.new_content,
            template_name=template_name,
            retained_fields=result.retained_fields,
        )
        resources: List[EmbeddedResource] = [
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=f"file:///{file_path.lstrip('/')}",
                    mimeType=_get_mime_type(file_path),
                    text=result.new_content,
                ),
            ),
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=f"file:///{bundle['audit_log_path'].lstrip('/')}",
                    mimeType="application/x-ndjson",
                    text=bundle["audit_log_text"],
                ),
            ),
        ]
        if bundle.get("snapshot_path") and bundle.get("snapshot_text") is not None:
            resources.append(
                EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=f"file:///{bundle['snapshot_path'].lstrip('/')}",
                        mimeType="text/plain",
                        text=bundle["snapshot_text"],
                    ),
                )
            )
        return resources

    return result.model_dump()


@mcp.tool()
def get_audit_trail(file_path: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve audit history of changes made to the client workspace, including diffs and snapshot references.

    Args:
        file_path: Optional filter to see changes for a specific file.
        limit: Max number of recent entries to return (default 50).
    """
    entries = audit_manager.get_audit_trail(file_path=file_path, limit=limit)
    return [e.model_dump() for e in entries]


@mcp.tool()
def rollback_change(audit_id: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Roll back a previous modification in the client workspace using its audit trail snapshot.

    Args:
        audit_id: UUID of the audit entry to roll back.
        file_path: Optional path to the client workspace file. When provided, allows restoring from the client's local audit trail even if server logs are lost.
    """
    success, message = audit_manager.rollback(audit_id, file_path=file_path)
    restored_content = audit_manager.get_snapshot_content(audit_id, file_path=file_path)
    return {
        "success": success,
        "message": message,
        "audit_id": audit_id,
        "restored_content": restored_content,
    }


@mcp.tool()
def expand_audit_log(
    file_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Expand and format audit_log.jsonl into an indented JSON array file (audit_log.json) on request.

    Args:
        file_path: Optional path to a file in the workspace to format its local audit log. If omitted, formats the server's audit log.
        output_path: Optional custom path for the generated JSON file. Defaults to 'audit_log.json' in the same audit directory.
    """
    success, message, json_path = audit_manager.expand_audit_log(
        file_path=file_path,
        output_path=output_path,
    )
    return {
        "success": success,
        "message": message,
        "json_path": json_path,
    }


@mcp.tool()
def get_template_repository_info() -> Dict[str, Any]:
    """Retrieve Git submodule status for the templates repository, including commit hash and remote URL."""
    return registry.get_submodule_info()


# ==========================================
# MCP RESOURCES & RESOURCE TEMPLATES
# ==========================================

@mcp.resource("template://list")
def resource_template_list() -> str:
    """Resource listing all available templates and metadata."""
    templates = registry.list_templates()
    return json.dumps([t.model_dump() for t in templates], indent=2)


@mcp.resource("template://{template_name}")
def resource_template_detail(template_name: str) -> str:
    """Resource providing raw Jinja2 template source code and schema metadata."""
    meta = registry.get_template_metadata(template_name)
    if not meta:
        return json.dumps({"error": f"Template '{template_name}' not found."})
    return json.dumps(meta.model_dump(), indent=2)


@mcp.resource("audit://trail")
def resource_audit_trail() -> str:
    """Resource providing recent audit log entries."""
    entries = audit_manager.get_audit_trail(limit=25)
    return json.dumps([e.model_dump() for e in entries], indent=2)


@mcp.resource("audit://entry/{entry_id}")
def resource_audit_entry(entry_id: str) -> str:
    """Resource returning a single audit entry with its full diff and metadata."""
    entry = audit_manager.get_entry(entry_id)
    if not entry:
        return json.dumps({"error": f"Audit entry '{entry_id}' not found."})
    return json.dumps(entry.model_dump(), indent=2)


# ==========================================
# MCP PROMPTS
# ==========================================

@mcp.prompt("generate-file")
def prompt_generate_file(template_name: str, target_path: str) -> str:
    """Guided prompt to help user choose template parameters and generate a new file."""
    meta = registry.get_template_metadata(template_name)
    params_info = ""
    if meta and meta.parameters:
        params_info = "\nExpected Parameters:\n" + "\n".join(
            f"- {k} ({v.get('type', 'any')}): {v.get('description', '')} [default: {v.get('default')}]"
            for k, v in meta.parameters.items()
        )
    return (
        f"You are scaffolding a new file at '{target_path}' using the template '{template_name}'.\n"
        f"{params_info}\n\n"
        f"1. Ask the user for any specific values for the parameters above or confirm if defaults should be used.\n"
        f"2. Use `render_template` to preview the result.\n"
        f"3. Call `generate_file` with template_name='{template_name}' and target_path='{target_path}' to receive the rendered EmbeddedResource.\n"
        f"4. IMPORTANT: Use your local client workspace toolbox (e.g. write_file) to write the returned resource text into '{target_path}'."
    )


@mcp.prompt("compare-with-template")
def prompt_compare(file_path: str, template_name: str) -> str:
    """Guided prompt to analyze drift between workspace file and latest server template."""
    return (
        f"You are checking for drift between the client file at '{file_path}' and the standard template '{template_name}'.\n"
        f"1. Call `compare_workspace_file` with file_path='{file_path}' and template_name='{template_name}'.\n"
        f"2. Review the added fields, removed custom fields, and modified values.\n"
        f"3. Summarize differences clearly for the user and recommend whether a migration is needed."
    )


@mcp.prompt("migrate-file")
def prompt_migrate_file(file_path: str, template_name: str) -> str:
    """Guided prompt to safely migrate an existing workspace file to the latest template schema."""
    return (
        f"You are helping the user migrate '{file_path}' to the latest template '{template_name}' while preserving user data.\n"
        f"1. Call `migrate_file` with dry_run=True to preview retained fields and the unified diff.\n"
        f"2. Present the retained field values and proposed changes to the user for confirmation.\n"
        f"3. Once confirmed, execute `migrate_file` with dry_run=False.\n"
        f"4. Note the returned audit_id and remind the user they can rollback anytime with `rollback_change`."
    )


@mcp.prompt("audit-review")
def prompt_audit_review(file_path: Optional[str] = None) -> str:
    """Guided prompt to review client modifications and step-by-step audit history."""
    filter_msg = f" for '{file_path}'" if file_path else ""
    return (
        f"You are reviewing the audit trail of modifications{filter_msg}.\n"
        f"1. Call `get_audit_trail` to list recent actions and unified diffs.\n"
        f"2. Walk the user through what changed, when it changed, and what fields were retained.\n"
        f"3. If any unintended change occurred, suggest using `rollback_change` with the audit_id."
    )


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["sse", "streamable-http", "stdio"], case_sensitive=False),
    default=lambda: os.environ.get("MCP_TRANSPORT", "sse"),
    help="MCP transport protocol (default: sse)",
)
@click.option(
    "--host",
    default=lambda: os.environ.get("MCP_HOST", "127.0.0.1"),
    help="Host to bind for HTTP/SSE (default: 127.0.0.1)",
)
@click.option(
    "--port",
    default=lambda: int(os.environ.get("MCP_PORT", 8000)),
    type=int,
    help="Port to bind for HTTP/SSE (default: 8000)",
)
def main(transport: str, host: str, port: int) -> None:
    """Main entrypoint for running the MCP server."""
    if audit_manager not in mcp.middleware:
        mcp.middleware.append(audit_manager)

    transport_mode = transport.lower()
    if transport_mode == "stdio":
        mcp.run(transport="stdio")
    elif transport_mode == "sse":
        print(f"Starting Template MCP Server (SSE) on http://{host}:{port}/sse", file=sys.stderr)
        mcp.run(transport="sse", host=host, port=port)
    elif transport_mode == "streamable-http":
        print(f"Starting Template MCP Server (Streamable HTTP) on http://{host}:{port}/mcp", file=sys.stderr)
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        raise ValueError(f"Unsupported transport: {transport}")


if __name__ == "__main__":
    main()
