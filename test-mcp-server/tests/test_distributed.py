"""Unit tests for distributed client-server execution.

Verifies:
1. In-band content passing (`current_content`) for comparison and migration with zero server disk access.
2. Multi-resource EmbeddedResource bundling for client workspace audit log and snapshots.
3. Client-side writing and rollback restoration from returned resources.
"""

from pathlib import Path
import json
import pytest

from template_mcp_server.engine.audit import AuditManager
from template_mcp_server.engine.comparator import TextComparator
from template_mcp_server.engine.generator import TemplateGenerator
from template_mcp_server.engine.migrator import TemplateMigrator
from template_mcp_server.models.schemas import AuditAction
from template_mcp_server.server import (
    compare_workspace_file,
    generate_file,
    generate_files,
    migrate_file,
    rollback_change,
)
from template_mcp_server.templates.registry import TemplateRegistry


@pytest.fixture
def clean_audit_manager(tmp_path):
    server_audit_dir = tmp_path / "server_audit"
    return AuditManager(base_dir=str(server_audit_dir))


def test_distributed_comparison_in_memory():
    """Verify comparing remote client file with current_content does not access server disk."""
    remote_path = "/nonexistent/remote/client/workspace/app_config.yaml"
    client_content = """
app:
  name: "distributed_app"
  version: "0.9.0"
  debug: false
"""
    # Calling compare_workspace_file with current_content should succeed without FileNotFoundError
    res = compare_workspace_file(
        file_path=remote_path,
        template_name="config_yaml",
        current_content=client_content,
    )
    assert "error" not in res
    assert res["identical"] is False
    assert res["drift_detected"] is True
    # Server path should definitely not exist
    assert not Path(remote_path).exists()


def test_distributed_comparison_identical():
    """Verify identical detection in memory for non-existent server path."""
    registry = TemplateRegistry()
    template_source = registry.get_template_source("markdown_doc")
    # Render default
    rendered = TemplateGenerator(registry).render("markdown_doc", {})

    remote_path = "/nonexistent/remote/client/README.md"
    res = compare_workspace_file(
        file_path=remote_path,
        template_name="markdown_doc",
        current_content=rendered,
    )
    assert res["identical"] is True
    assert res["drift_detected"] is False


def test_distributed_migration_in_memory():
    """Verify migration using current_content produces new_content and diff without writing to server disk."""
    remote_path = "/nonexistent/remote/client/billing_service.py"
    client_content = """# billing service
service_name = "billing_service"
port = 7000
host = "0.0.0.0"
"""
    res = migrate_file(
        file_path=remote_path,
        template_name="python_service",
        current_content=client_content,
        extra_updates={"port": 7001},
        dry_run=False,
    )

    assert isinstance(res, dict)
    assert res["success"] is True
    assert res["retained_fields"]["service_name"] == "billing_service"
    assert res["retained_fields"]["port"] == 7001
    assert res["new_content"] is not None
    assert "billing_service" in res["new_content"]
    assert "7001" in res["new_content"]
    assert res["audit_id"] is not None

    # Crucial: server disk must not have been touched
    assert not Path(remote_path).exists()


def test_distributed_migration_with_embedded_resources(tmp_path):
    """Verify migrate_file with return_resources=True returns code, audit log, and snapshot."""
    client_ws = tmp_path / "mock_client_workspace"
    client_ws.mkdir()
    client_file = client_ws / "payment_service.py"
    original_code = "service_name = 'payment_svc'\nport = 5000\n"

    res = migrate_file(
        file_path=str(client_file),
        template_name="python_service",
        current_content=original_code,
        extra_updates={"port": 5005},
        return_resources=True,
    )

    assert isinstance(res, list)
    # Expected: 1 code resource, 1 audit log resource, 1 rollback snapshot resource
    assert len(res) == 3

    code_res = res[0]
    audit_res = res[1]
    snap_res = res[2]

    assert code_res.type == "resource"
    assert "payment_service.py" in code_res.resource.uri
    assert "5005" in code_res.resource.text

    assert audit_res.type == "resource"
    assert "audit_log.jsonl" in audit_res.resource.uri
    assert audit_res.resource.mime_type == "application/x-ndjson"

    assert snap_res.type == "resource"
    assert "snapshots" in snap_res.resource.uri
    assert snap_res.resource.text == original_code

    # Simulate client writing the returned resources to its local workspace
    for r in res:
        # Extract path from uri (strip file:///)
        uri_str = r.resource.uri.replace("file:///", "/")
        target_path = Path(uri_str)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(r.resource.text, encoding="utf-8")

    # Verify client workspace files
    assert client_file.exists()
    assert "5005" in client_file.read_text(encoding="utf-8")

    client_audit_log = client_ws / ".mcp_audit" / "audit_log.jsonl"
    assert client_audit_log.exists()
    audit_data = json.loads(client_audit_log.read_text(encoding="utf-8").strip())
    assert audit_data["action"] == "MIGRATE"
    assert audit_data["retained_fields"]["port"] == 5005


def test_distributed_generation_with_current_content(tmp_path):
    """Verify generate_file bundles code, client audit log, and snapshot when replacing existing content."""
    client_ws = tmp_path / "client_ws"
    client_ws.mkdir()
    target_path = client_ws / "worker.py"
    previous_content = "# Old custom worker script\nWORKER_ID = 1\n"

    resources = generate_file(
        template_name="python_service",
        target_path=str(target_path),
        context={"service_name": "worker_service", "port": 6000},
        current_content=previous_content,
        include_client_audit=True,
    )

    # 3 resources: code file, audit log, snapshot
    assert len(resources) == 3
    code_res, audit_res, snap_res = resources[0], resources[1], resources[2]

    assert "worker.py" in code_res.resource.uri
    assert "worker_service" in code_res.resource.text

    assert "audit_log.jsonl" in audit_res.resource.uri
    assert audit_res.resource.mime_type == "application/x-ndjson"

    assert "snapshots" in snap_res.resource.uri
    assert snap_res.resource.text == previous_content


def test_distributed_generation_without_audit():
    """Verify include_client_audit=False returns strictly the generated code file."""
    resources = generate_file(
        template_name="python_service",
        target_path="standalone.py",
        context={"service_name": "standalone_svc"},
        include_client_audit=False,
    )
    assert len(resources) == 1
    assert "standalone.py" in resources[0].resource.uri
    assert "standalone_svc" in resources[0].resource.text


def test_distributed_rollback_returns_restored_content(tmp_path):
    """Verify rollback_change returns restored_content so remote client can restore local files."""
    remote_path = str(tmp_path / "remote_app.py")
    original_code = "service_name = 'initial_app'\nport = 3000\n"

    mig_result = migrate_file(
        file_path=remote_path,
        template_name="python_service",
        current_content=original_code,
        extra_updates={"port": 3001},
        dry_run=False,
    )
    audit_id = mig_result["audit_id"]

    # Roll back the change
    rb_res = rollback_change(audit_id=audit_id, file_path=remote_path)
    assert rb_res["success"] is True
    assert rb_res["audit_id"] == audit_id
    # Server should return the restored content from its snapshot
    assert rb_res.get("restored_content") == original_code


def test_create_audit_bundle_relative_and_absolute(clean_audit_manager):
    """Test create_audit_bundle computes correct relative and absolute paths."""
    # Test relative path
    bundle_rel = clean_audit_manager.create_audit_bundle(
        action=AuditAction.GENERATE,
        file_path="src/components/button.py",
        previous_content="class OldButton: pass",
        new_content="class NewButton: pass",
        template_name="python_service",
    )
    assert bundle_rel["audit_log_path"] == ".mcp_audit/audit_log.jsonl"
    assert bundle_rel["snapshot_path"].startswith(".mcp_audit/snapshots/")
    assert bundle_rel["snapshot_filename"].endswith("_button.py")
    assert bundle_rel["snapshot_text"] == "class OldButton: pass"
    assert '"action":"GENERATE"' in bundle_rel["audit_log_text"]

    # Test absolute path
    bundle_abs = clean_audit_manager.create_audit_bundle(
        action=AuditAction.MIGRATE,
        file_path="/workspace/project/src/models.py",
        previous_content="x = 1",
        new_content="x = 2",
        template_name="python_service",
    )
    assert "audit_log.jsonl" in bundle_abs["audit_log_path"]
    assert "snapshots" in bundle_abs["snapshot_path"]
    assert bundle_abs["snapshot_filename"].endswith("_models.py")


def test_create_audit_bundle_skips_client_disk_writes(clean_audit_manager, tmp_path):
    """Verify create_audit_bundle records on server but skips direct disk writes to client paths."""
    client_ws = tmp_path / "mock_client"
    client_ws.mkdir()
    client_file = client_ws / "remote_doc.md"

    bundle = clean_audit_manager.create_audit_bundle(
        action=AuditAction.GENERATE,
        file_path=str(client_file),
        previous_content="old doc",
        new_content="new doc",
        template_name="markdown_doc",
    )

    # Server audit log must exist
    assert clean_audit_manager.log_file.exists()

    # Client directory on server disk must NOT have been touched
    assert not (client_ws / ".mcp_audit").exists()

    # But the bundle payload is complete and ready for client delivery
    assert bundle["audit_log_path"] == str(client_ws / ".mcp_audit" / "audit_log.jsonl")
    assert bundle["snapshot_text"] == "old doc"
    assert '"action":"GENERATE"' in bundle["audit_log_text"]
