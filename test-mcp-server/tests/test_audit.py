import json

from template_mcp_server.models.schemas import AuditAction


def test_audit_record_and_rollback(audit_manager, temp_workspace):
    test_file = temp_workspace / "app.conf"
    initial_text = "VERSION=1.0\nDEBUG=True\n"
    test_file.write_text(initial_text, encoding="utf-8")

    modified_text = "VERSION=2.0\nDEBUG=False\n"
    test_file.write_text(modified_text, encoding="utf-8")

    entry = audit_manager.record_action(
        action=AuditAction.MIGRATE,
        file_path=str(test_file),
        previous_content=initial_text,
        new_content=modified_text,
        template_name="app_config",
        retained_fields={"VERSION": "1.0"},
    )

    assert entry.id is not None
    assert entry.snapshot_path is not None
    assert "VERSION=1.0" in entry.diff
    assert "VERSION=2.0" in entry.diff

    # Verify retrieval
    history = audit_manager.get_audit_trail(file_path=str(test_file))
    assert len(history) == 1
    assert history[0].id == entry.id

    # Test rollback
    success, msg = audit_manager.rollback(entry.id)
    assert success is True
    assert test_file.read_text(encoding="utf-8") == initial_text

    # Verify rollback was itself logged to the audit trail
    new_history = audit_manager.get_audit_trail(file_path=str(test_file))
    assert len(new_history) == 2
    assert new_history[0].action == AuditAction.ROLLBACK


def test_audit_rollback_newly_created_file(audit_manager, temp_workspace):
    new_file = temp_workspace / "created.txt"
    content = "Hello World"
    new_file.write_text(content, encoding="utf-8")

    entry = audit_manager.record_action(
        action=AuditAction.GENERATE,
        file_path=str(new_file),
        previous_content=None,
        new_content=content,
        template_name="hello",
    )

    assert new_file.exists()
    success, msg = audit_manager.rollback(entry.id)
    assert success is True
    assert not new_file.exists()


def test_client_workspace_independent_audit_trail_and_rollback(audit_manager, temp_workspace):
    """Test that client workspace receives audit logs and snapshots, allowing rollback even if server data is lost."""
    import shutil
    import tempfile
    from pathlib import Path
    from template_mcp_server.engine.audit import AuditManager

    client_ws = Path(tempfile.mkdtemp(prefix="client_ws_"))
    try:
        # Mark as a project workspace with pyproject.toml
        (client_ws / "pyproject.toml").write_text("[project]\nname='client_app'\n", encoding="utf-8")
        client_file = client_ws / "app.py"
        original_code = "def start():\n    print('v1')\n"
        client_file.write_text(original_code, encoding="utf-8")

        migrated_code = "def start():\n    print('v2')\n"
        client_file.write_text(migrated_code, encoding="utf-8")

        # Record action
        entry = audit_manager.record_action(
            action=AuditAction.MIGRATE,
            file_path=str(client_file),
            previous_content=original_code,
            new_content=migrated_code,
            template_name="python_service",
        )

        # Verify audit trail exists on server
        assert audit_manager.log_file.exists()

        # Verify audit trail and snapshot exist in client workspace (JSONL only by default)
        client_audit_dir = client_ws / ".mcp_audit"
        assert client_audit_dir.exists()
        assert (client_audit_dir / "audit_log.jsonl").exists()
        assert not (client_audit_dir / "audit_log.json").exists(), "audit_log.json must not be created automatically"
        assert (client_audit_dir / "snapshots").exists()
        client_snapshots = list((client_audit_dir / "snapshots").glob("*"))
        assert len(client_snapshots) == 1
        assert client_snapshots[0].read_text(encoding="utf-8") == original_code

        # Expand JSONL when requested by user
        success, msg, json_path = audit_manager.expand_audit_log(file_path=str(client_file))
        assert success is True
        assert (client_audit_dir / "audit_log.json").exists()
        expanded_data = json.loads((client_audit_dir / "audit_log.json").read_text(encoding="utf-8"))
        assert isinstance(expanded_data, list)
        assert len(expanded_data) == 1
        assert expanded_data[0]["id"] == entry.id

        # SIMULATE COMPLETE SERVER AUDIT DATA LOSS
        shutil.rmtree(audit_manager.audit_dir)
        assert not audit_manager.audit_dir.exists()

        # Audit trail must still be retrievable from client workspace
        trail = audit_manager.get_audit_trail(file_path=str(client_file))
        assert len(trail) >= 1
        assert trail[0].id == entry.id
        assert "print('v1')" in trail[0].diff

        # Rollback must succeed using ONLY the client workspace snapshot
        success, msg = audit_manager.rollback(entry.id, file_path=str(client_file))
        assert success is True
        assert client_file.read_text(encoding="utf-8") == original_code

    finally:
        shutil.rmtree(client_ws, ignore_errors=True)


def test_client_workspace_with_hyphenated_mcp_audit_dir(audit_manager):
    """Test that a client workspace using '.mcp-audit' directory is respected and used."""
    import shutil
    import tempfile
    from pathlib import Path

    client_ws = Path(tempfile.mkdtemp(prefix="client_hyphen_ws_"))
    try:
        # Pre-create .mcp-audit directory
        custom_audit_dir = client_ws / ".mcp-audit"
        custom_audit_dir.mkdir(parents=True, exist_ok=True)

        client_file = client_ws / "settings.yaml"
        client_file.write_text("env: development\n", encoding="utf-8")

        new_text = "env: production\n"
        client_file.write_text(new_text, encoding="utf-8")

        entry = audit_manager.record_action(
            action=AuditAction.MIGRATE,
            file_path=str(client_file),
            previous_content="env: development\n",
            new_content=new_text,
            template_name="config_yaml",
        )

        # Should be stored in .mcp-audit
        assert (custom_audit_dir / "audit_log.jsonl").exists()
        assert (custom_audit_dir / "snapshots").exists()

        # Rollback works
        success, msg = audit_manager.rollback(entry.id, file_path=str(client_file))
        assert success is True
        assert client_file.read_text(encoding="utf-8") == "env: development\n"
    finally:
        shutil.rmtree(client_ws, ignore_errors=True)

