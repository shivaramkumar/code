import pytest

from template_mcp_server.server import (
    compare_text,
    extract_fields,
    expand_audit_log,
    generate_file,
    generate_files,
    get_audit_trail,
    get_template_schema,
    list_templates,
    migrate_file,
    prompt_generate_file,
    prompt_migrate_file,
    render_template,
    resource_template_detail,
    resource_template_list,
    rollback_change,
)


def test_list_templates_tool():
    templates = list_templates()
    assert isinstance(templates, list)
    assert len(templates) >= 4
    names = [t["name"] for t in templates]
    assert "config_yaml" in names
    assert "python_service" in names


def test_get_template_schema_tool():
    schema = get_template_schema("config_yaml")
    assert schema["name"] == "config_yaml"
    assert "parameters" in schema
    assert "app_name" in schema["parameters"]


def test_render_template_tool():
    rendered = render_template("markdown_doc", {"title": "Test Title"})
    assert "# Test Title" in rendered


def test_generate_and_audit_tools(temp_workspace):
    target = temp_workspace / "service.py"
    resources = generate_file(
        template_name="python_service",
        target_path=str(target),
        context={"service_name": "billing_api", "port": 8081},
    )
    # Returns generated file + client audit log entry
    assert len(resources) == 2
    res = resources[0]
    audit_res = resources[1]
    assert res.type == "resource"
    assert "billing_api" in res.resource.text
    assert res.resource.mime_type == "text/x-python"
    assert "service.py" in res.resource.uri
    assert "audit_log.jsonl" in audit_res.resource.uri
    assert audit_res.resource.mime_type == "application/x-ndjson"

    # Client receives EmbeddedResource bundle and writes it to workspace
    target.write_text(res.resource.text, encoding="utf-8")
    client_audit_dir = temp_workspace / ".mcp_audit"
    client_audit_dir.mkdir(parents=True, exist_ok=True)
    (client_audit_dir / "audit_log.jsonl").write_text(audit_res.resource.text, encoding="utf-8")

    # Check audit trail tool
    trail = get_audit_trail(file_path=str(target))
    assert len(trail) >= 1

    # Check extract_fields tool
    fields = extract_fields(target.read_text(encoding="utf-8"), "python")
    assert fields.get("service_name") == "billing_api"
    assert fields.get("port") == 8081

    # Check migrate_file tool
    mig_result = migrate_file(
        file_path=str(target),
        template_name="python_service",
        extra_updates={"port": 8082},
    )
    assert mig_result["success"] is True
    assert mig_result["retained_fields"]["service_name"] == "billing_api"
    assert mig_result["retained_fields"]["port"] == 8082

    # Check rollback_change tool
    rb_res = rollback_change(mig_result["audit_id"], file_path=str(target))
    assert rb_res["success"] is True
    restored_fields = extract_fields(target.read_text(encoding="utf-8"), "python")
    assert restored_fields.get("port") == 8081

    # Check expand_audit_log tool
    expand_res = expand_audit_log(file_path=str(target))
    assert expand_res["success"] is True
    assert expand_res["json_path"] is not None
    assert "Successfully expanded" in expand_res["message"]


def test_generate_files_batch_embedded_resource():
    files = [
        {"path": "reports/summary.txt", "text": "blablabla"},
        {"path": "reports/detail.txt", "text": "more text"},
        {"template_name": "config_yaml", "path": "config.yaml", "context": {"app_name": "batch_app"}},
    ]
    # Pure code file batch generation without audit bundle
    results = generate_files(files=files, include_client_audit=False)
    assert len(results) == 3

    assert results[0].type == "resource"
    assert results[0].resource.uri == "file:///reports/summary.txt"
    assert results[0].resource.mime_type == "text/plain"
    assert results[0].resource.text == "blablabla"

    assert results[1].type == "resource"
    assert results[1].resource.uri == "file:///reports/detail.txt"
    assert results[1].resource.text == "more text"

    assert results[2].type == "resource"
    assert results[2].resource.uri == "file:///config.yaml"
    assert "batch_app" in results[2].resource.text
    assert results[2].resource.mime_type == "application/x-yaml"

    # Batch generation with client audit bundle enabled
    results_with_audit = generate_files(files=files, include_client_audit=True)
    assert len(results_with_audit) >= 4
    uris = [r.resource.uri for r in results_with_audit]
    assert any("audit_log.jsonl" in u for u in uris)


def test_prompts():
    prompt_str = prompt_generate_file("config_yaml", "app/config.yaml")
    assert "config_yaml" in prompt_str
    assert "app/config.yaml" in prompt_str

    mig_prompt = prompt_migrate_file("service.py", "python_service")
    assert "service.py" in mig_prompt
    assert "dry_run=True" in mig_prompt


def test_resources():
    list_json = resource_template_list()
    assert "config_yaml" in list_json

    detail_json = resource_template_detail("config_yaml")
    assert "config_yaml" in detail_json


@pytest.mark.asyncio
async def test_audit_manager_middleware():
    from unittest.mock import MagicMock
    from template_mcp_server.server import audit_manager, mcp

    # 1. Verify audit_manager is registered in mcp.middleware
    assert audit_manager in mcp.middleware

    # 2. Verify middleware wraps and executes tool calls
    ctx = MagicMock()
    ctx.method = "tools/call"
    ctx.params = {"name": "test_tool", "arguments": {}}

    async def mock_tool_next(req_ctx):
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}

    res = await audit_manager(ctx, mock_tool_next)
    assert res["isError"] is False
    assert res["content"][0]["text"] == "ok"

    # 3. Verify middleware propagates exceptions correctly
    async def mock_failing_next(req_ctx):
        raise ValueError("Simulated tool error")

    with pytest.raises(ValueError, match="Simulated tool error"):
        await audit_manager(ctx, mock_failing_next)

    # 4. Verify non-tool methods pass through
    init_ctx = MagicMock()
    init_ctx.method = "initialize"

    async def mock_init_next(req_ctx):
        return {"capabilities": {}}

    init_res = await audit_manager(init_ctx, mock_init_next)
    assert init_res == {"capabilities": {}}

