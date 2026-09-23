"""Tests for FieldExtractor and TextComparator."""

from template_mcp_server.engine.comparator import FieldExtractor, TextComparator


def test_field_extractor_yaml():
    yaml_content = """
app:
  name: "demo-service"
  version: "2.1.0"
server:
  port: 7070
  debug: false
"""
    fields = FieldExtractor.extract(yaml_content, "yaml")
    assert fields.get("name") == "demo-service"
    assert fields.get("version") == "2.1.0"
    assert fields.get("port") == 7070
    assert fields.get("debug") is False


def test_field_extractor_python():
    py_content = """
SERVICE_NAME = "users_api"
VERSION = "3.0.0"
PORT = 8080
ENABLE_METRICS = False
"""
    fields = FieldExtractor.extract(py_content, "python")
    assert fields.get("service_name") == "users_api"
    assert fields.get("version") == "3.0.0"
    assert fields.get("port") == 8080
    assert fields.get("enable_metrics") is False


def test_field_extractor_markdown():
    md_content = """# My Cool Project

This is a comprehensive overview of the system.

## Author
Alice Dev

## License
Apache-2.0
"""
    fields = FieldExtractor.extract(md_content, "markdown")
    assert fields.get("title") == "My Cool Project"
    assert fields.get("author") == "Alice Dev"
    assert "comprehensive overview" in fields.get("description", "")


def test_comparator_detects_drift(comparator):
    modified_text = """# Application Configuration
app:
  name: "custom-app"
  version: "1.0.0"
  environment: "staging"

server:
  port: 9999
  debug: false
  log_level: "DEBUG"

database:
  url: "sqlite:///app.db"
  pool_size: 10
"""
    result = comparator.compare_with_template("config_yaml", modified_text)
    assert result.drift_detected is True
    assert "port" in result.modified_fields
    assert result.modified_fields["port"]["client_value"] == 9999
    assert result.modified_fields["port"]["model_value"] == 8080
    assert result.unified_diff != ""


def test_comparator_identical_content(generator, comparator):
    rendered = generator.render("config_yaml")
    result = comparator.compare_with_template("config_yaml", rendered)
    assert result.identical is True
    assert result.drift_detected is False
