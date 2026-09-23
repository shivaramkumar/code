"""Tests for TemplateMigrator."""


def test_migrator_retains_client_fields(migrator, temp_workspace):
    # Setup legacy client file
    legacy_file = temp_workspace / "old_service.py"
    legacy_content = """# Legacy service implementation
SERVICE_NAME = "payments_gateway"
VERSION = "1.0.0-rc1"
PORT = 9443
AUTHOR = "SecurityTeam"
"""
    legacy_file.write_text(legacy_content, encoding="utf-8")

    # Migrate to latest 'python_service' template
    res = migrator.migrate_file(
        file_path=str(legacy_file),
        template_name="python_service",
        dry_run=False,
    )

    assert res.success is True
    assert res.audit_id is not None
    assert res.retained_fields["service_name"] == "payments_gateway"
    assert res.retained_fields["port"] == 9443
    assert res.retained_fields["author"] == "SecurityTeam"

    # Verify updated content on disk
    updated_content = legacy_file.read_text(encoding="utf-8")
    assert 'SERVICE_NAME = "payments_gateway"' in updated_content
    assert "PORT = 9443" in updated_content
    assert 'AUTHOR = "SecurityTeam"' in updated_content
    # New template features included
    assert "class ServiceConfig:" in updated_content
    assert "def get_status() -> dict:" in updated_content


def test_migrator_dry_run_preserves_file(migrator, temp_workspace):
    file_path = temp_workspace / "config.yaml"
    initial_content = "app:\n  name: 'my-custom-name'\n  port: 5000\n"
    file_path.write_text(initial_content, encoding="utf-8")

    res = migrator.migrate_file(
        file_path=str(file_path),
        template_name="config_yaml",
        dry_run=True,
    )

    assert res.success is True
    assert res.dry_run is True
    assert res.audit_id is None
    # File content remains untouched
    assert file_path.read_text(encoding="utf-8") == initial_content
    # Diff generated
    assert res.diff != ""
