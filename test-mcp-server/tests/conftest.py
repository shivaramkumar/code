"""Test fixtures and setup."""

import shutil
import tempfile
from pathlib import Path
import pytest

from template_mcp_server.engine.audit import AuditManager
from template_mcp_server.engine.comparator import TextComparator
from template_mcp_server.engine.generator import TemplateGenerator
from template_mcp_server.engine.migrator import TemplateMigrator
from template_mcp_server.templates.registry import TemplateRegistry


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    tmpdir = tempfile.mkdtemp(prefix="mcp_test_ws_")
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def registry():
    """Return template registry with built-in templates."""
    return TemplateRegistry()


@pytest.fixture
def audit_manager(temp_workspace):
    """Return AuditManager configured with temp workspace."""
    audit_dir = temp_workspace / ".mcp_audit"
    return AuditManager(base_dir=str(audit_dir))


@pytest.fixture
def generator(registry, audit_manager):
    """Return TemplateGenerator."""
    return TemplateGenerator(registry, audit_manager)


@pytest.fixture
def comparator(registry):
    """Return TextComparator."""
    return TextComparator(registry)


@pytest.fixture
def migrator(registry, generator, audit_manager):
    """Return TemplateMigrator."""
    return TemplateMigrator(registry, generator, audit_manager)
