"""Tests for TemplateGenerator."""

from pathlib import Path


def test_list_templates(registry):
    templates = registry.list_templates()
    names = [t.name for t in templates]
    assert "config_yaml" in names
    assert "python_service" in names
    assert "docker_compose" in names
    assert "markdown_doc" in names


def test_render_with_defaults(generator):
    rendered = generator.render("config_yaml")
    assert "name: \"my-application\"" in rendered
    assert "port: 8080" in rendered
    assert "debug: true" in rendered


def test_render_with_custom_context(generator):
    context = {
        "app_name": "custom-service",
        "port": 9090,
        "debug": False,
        "database_url": "postgresql://localhost/db",
    }
    rendered = generator.render("config_yaml", context)
    assert "name: \"custom-service\"" in rendered
    assert "port: 9090" in rendered
    assert "debug: false" in rendered
    assert "url: \"postgresql://localhost/db\"" in rendered


def test_generate_file_new_and_overwrite(generator, temp_workspace):
    target = temp_workspace / "config.yaml"
    success, msg, audit_id = generator.generate_file(
        template_name="config_yaml",
        target_path=str(target),
        context={"app_name": "test-app"},
        overwrite=False,
    )
    assert success is True
    assert audit_id is not None
    assert target.exists()
    assert "test-app" in target.read_text(encoding="utf-8")

    # Attempt to overwrite without flag
    success2, msg2, _ = generator.generate_file(
        template_name="config_yaml",
        target_path=str(target),
        context={"app_name": "new-name"},
        overwrite=False,
    )
    assert success2 is False
    assert "already exists" in msg2

    # Overwrite with flag
    success3, msg3, audit_id3 = generator.generate_file(
        template_name="config_yaml",
        target_path=str(target),
        context={"app_name": "new-name"},
        overwrite=True,
    )
    assert success3 is True
    assert "new-name" in target.read_text(encoding="utf-8")
