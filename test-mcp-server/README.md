# MCP Template & Migration Server for VS Code

A Model Context Protocol (MCP) server designed for VS Code clients (including native VS Code MCP, Cline, Roo Code, GitHub Copilot, and Continue).

The server equips your AI assistant with tools, resources, templates, and prompts to:
1. **Generate**: Scaffold files in the client workspace using flexible Jinja2 templates and validated schemas.
2. **Compare**: Detect drift, structural changes, and differences between workspace files and server models/templates.
3. **Migrate**: Upgrade existing workspace files to newer template versions while **strictly preserving** existing user-defined values and settings.
4. **Audit Trail & Rollback**: Automatically record all client-side file changes with timestamps, unified diffs, SHA-256 hashes, and file snapshots—enabling instant rollback at any time.

---

## Quick Start for VS Code

### 1. Requirements & Setup
- Python 3.13+ managed with `uv` (recommended):
  ```bash
  uv venv --python 3.13
  uv pip install -e ".[dev]"
  ```
  *(Or using standard python3 venv: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" `)*

### 2. VS Code Configuration (`.vscode/mcp.json`)
The project includes a ready-to-use `.vscode/mcp.json` file:

```json
{
  "servers": {
    "template-migrator": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "template_mcp_server.server", "--transport", "stdio"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}/src",
        "MCP_AUDIT_DIR": "${workspaceFolder}/.mcp_audit"
      }
    }
  }
}
```

### 3. Cline / Roo Code Configuration
If using the Cline or Roo Code extension in VS Code, add the server to your MCP Settings (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "template-migrator": {
      "command": "/absolute/path/to/test-mcp-server/.venv/bin/python",
      "args": ["-m", "template_mcp_server.server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/test-mcp-server/src",
        "MCP_AUDIT_DIR": "/absolute/path/to/test-mcp-server/.mcp_audit"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

---

## MCP Primitives

### 🛠️ Tools

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `list_templates` | None | Lists all available Jinja2 templates, descriptions, and required schema parameters. |
| `get_template_schema` | `template_name` | Retrieves full schema and parameters for a specific template. |
| `render_template` | `template_name`, `context` | Preview/dry-run render of a Jinja2 template with context without touching the disk. |
| `generate_files` | `files`, `template_name`, `target_path`, `context` | Renders template(s) and returns them as `EmbeddedResource` objects without writing to disk. |
| `generate_file` | `template_name`, `target_path`, `context` | Renders a template and returns it as an `EmbeddedResource` without writing to disk. |
| `compare_text` | `template_name`, `current_text`, `model_data` | Compares arbitrary text or client code with a server template model, returning field diffs and unified diff. |
| `compare_workspace_file` | `file_path`, `template_name`, `model_data` | Compares an existing workspace file with a server template to detect drift. |
| `extract_fields` | `content`, `file_type` | Extracts structured fields from YAML, JSON, Python assignments, or Key-Value text. |
| `migrate_file` | `file_path`, `template_name`, `extra_updates`, `dry_run` | Upgrades a file to the latest template version while retaining custom field values. |
| `get_audit_trail` | `file_path`, `limit` | Returns the audit history of client modifications with diffs and timestamps. |
| `rollback_change` | `audit_id`, `file_path` | Restores a client file to the exact snapshot recorded prior to an audit step. |
| `expand_audit_log` | `file_path`, `output_path` | Expands and formats `audit_log.jsonl` into an indented JSON array file on demand. |

---

### 📦 Resources & Resource Templates

| URI | Description |
| :--- | :--- |
| `template://list` | JSON list of all registered templates and metadata. |
| `template://{template_name}` | Raw Jinja2 template source code and schema definition. |
| `audit://trail` | Recent audit trail log entries. |
| `audit://entry/{entry_id}` | Full details, diff, and snapshot info for a specific audit entry. |

---

### 💬 Prompts

- **`generate-file`**: Guides the AI assistant through parameter validation, previewing, and scaffolding files.
- **`compare-with-template`**: Instructs the AI assistant to inspect code drift against the official server template.
- **`migrate-file`**: Guides a safe migration process (dry-run review -> user confirmation -> execution).
- **`audit-review`**: Guides the AI assistant to inspect recent changes and suggest rollbacks if needed.

---

## Built-in Templates

The server includes pre-configured templates in `src/template_mcp_server/templates/builtin/`:
1. `config_yaml`: YAML application configuration (`app`, `server`, `database`, `logging`).
2. `python_service`: Python microservice boilerplate with config constants and health check.
3. `docker_compose`: Docker Compose configuration with application and PostgreSQL database.
4. `markdown_doc`: Standard documentation / README template.

### Adding Custom Templates
You can add your own templates by placing them in `.mcp-templates/<your_template_name>/` within your workspace:
- `template.<ext>.j2` (e.g. `template.yaml.j2`)
- `schema.json` (defines parameter names, types, descriptions, and defaults)

---

## Audit Trail & Rollback System

Every `generate_file` or `migrate_file` operation:
1. Takes an immutable snapshot of the existing file into `.mcp_audit/snapshots/`.
2. Computes unified diffs and SHA-256 hashes.
3. Logs the record into `.mcp_audit/audit_log.jsonl`.
4. Returns an `audit_id`.

To revert any change:
```python
rollback_change(audit_id="<UUID>")
```
The server restores the exact previous snapshot or removes the file if it was created from scratch.

---

## Running & Debugging

- **Debug in VS Code**: Press `F5` and select **"Debug MCP Server (stdio)"**.
- **Run Tests**:
  ```bash
  .venv/bin/pytest tests/ -v
  ```
