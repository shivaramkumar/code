"""Template registry with Git submodule discovery, version tracking, and schema caching."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import jinja2

from ..models.schemas import TemplateMetadata


class TemplateRegistry:
    """Discovers, loads, and manages Jinja2 templates from Git submodules and built-in fallbacks."""

    def __init__(
        self,
        submodule_templates_dir: Optional[str] = None,
        custom_templates_dir: Optional[str] = None,
    ):
        # 1. Submodule directory priority: constructor arg -> env var -> ./submodules/templates -> ./templates
        if submodule_templates_dir:
            self.submodule_dir = Path(submodule_templates_dir)
        elif os.environ.get("MCP_TEMPLATES_SUBMODULE_PATH"):
            self.submodule_dir = Path(os.environ["MCP_TEMPLATES_SUBMODULE_PATH"])
        elif (Path.cwd() / "submodules" / "templates").exists():
            self.submodule_dir = Path.cwd() / "submodules" / "templates"
        elif (Path.cwd() / "templates").exists():
            self.submodule_dir = Path.cwd() / "templates"
        else:
            self.submodule_dir = Path.cwd() / "submodules" / "templates"

        # 2. Built-in templates directory
        self.builtin_dir = Path(__file__).parent / "builtin"

        # 3. Custom workspace templates directory (optional user overrides)
        self.custom_dir = (
            Path(custom_templates_dir)
            if custom_templates_dir
            else Path(os.environ.get("MCP_TEMPLATES_DIR", Path.cwd() / ".mcp-templates"))
        )

        self._jinja_env: Optional[jinja2.Environment] = None
        self._templates_cache: Dict[str, TemplateMetadata] = {}
        self._template_sources: Dict[str, str] = {}
        self.reload()

    def get_submodule_info(self) -> Dict[str, Any]:
        """Inspect Git repository/submodule metadata (commit hash, branch, remote, status)."""
        info = {
            "path": str(self.submodule_dir.resolve() if self.submodule_dir.exists() else self.submodule_dir),
            "exists": self.submodule_dir.exists(),
            "is_git_repo": False,
            "commit_hash": None,
            "branch": None,
            "remote_url": None,
            "is_dirty": False,
        }

        if not self.submodule_dir.exists():
            return info

        git_indicator = self.submodule_dir / ".git"
        if not git_indicator.exists():
            # Check if parent is git repo and has submodule entry
            parent_git = self.submodule_dir.parent / ".git"
            if not parent_git.exists():
                return info

        try:
            # Get commit hash
            commit_res = subprocess.run(
                ["git", "-C", str(self.submodule_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if commit_res.returncode == 0:
                info["is_git_repo"] = True
                info["commit_hash"] = commit_res.stdout.strip()

            # Get branch or tag
            branch_res = subprocess.run(
                ["git", "-C", str(self.submodule_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if branch_res.returncode == 0:
                info["branch"] = branch_res.stdout.strip()

            # Get remote URL
            remote_res = subprocess.run(
                ["git", "-C", str(self.submodule_dir), "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if remote_res.returncode == 0:
                info["remote_url"] = remote_res.stdout.strip()

            # Check dirty status
            status_res = subprocess.run(
                ["git", "-C", str(self.submodule_dir), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if status_res.returncode == 0:
                info["is_dirty"] = bool(status_res.stdout.strip())
        except Exception:
            pass

        return info

    def reload(self) -> None:
        """Scan directories and load metadata and templates."""
        self._templates_cache.clear()
        self._template_sources.clear()

        submodule_info = self.get_submodule_info()
        commit_hash = submodule_info.get("commit_hash")

        # 1. Built-in templates (baseline)
        if self.builtin_dir.exists():
            self._scan_directory(self.builtin_dir)

        # 2. Submodule templates (override built-in)
        if self.submodule_dir.exists():
            self._scan_directory(self.submodule_dir, commit_hash=commit_hash)

        # 3. Custom workspace templates (optional overrides)
        if self.custom_dir.exists():
            self._scan_directory(self.custom_dir)

        # Setup Jinja environment with ChoiceLoader
        loaders = []
        if self.custom_dir.exists():
            loaders.append(jinja2.FileSystemLoader(str(self.custom_dir)))
        if self.submodule_dir.exists():
            loaders.append(jinja2.FileSystemLoader(str(self.submodule_dir)))
        if self.builtin_dir.exists():
            loaders.append(jinja2.FileSystemLoader(str(self.builtin_dir)))

        self._jinja_env = jinja2.Environment(
            loader=jinja2.ChoiceLoader(loaders) if loaders else jinja2.DictLoader({}),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _scan_directory(self, base_path: Path, commit_hash: Optional[str] = None) -> None:
        """Scan a folder containing template subfolders."""
        for item in base_path.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue

            schema_file = item / "schema.json"
            template_files = list(item.glob("*.j2"))
            if not template_files:
                continue

            template_file = template_files[0]
            template_name = item.name

            metadata_dict: Dict[str, Any] = {
                "name": template_name,
                "version": "1.0.0",
                "description": f"Template for {template_name}",
                "file_type": "text",
                "default_filename": template_file.stem,
                "parameters": {},
            }

            if schema_file.exists():
                try:
                    with open(schema_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        metadata_dict.update(loaded)
                except Exception:
                    pass

            raw_source = template_file.read_text(encoding="utf-8")
            metadata = TemplateMetadata(
                name=metadata_dict.get("name", template_name),
                version=str(metadata_dict.get("version", "1.0.0")),
                description=metadata_dict.get("description", ""),
                file_type=metadata_dict.get("file_type", "text"),
                default_filename=metadata_dict.get("default_filename", "output.txt"),
                parameters=metadata_dict.get("parameters", {}),
                raw_template=raw_source,
                submodule_commit=commit_hash,
            )

            self._templates_cache[template_name] = metadata
            self._template_sources[template_name] = raw_source

    @property
    def jinja_env(self) -> jinja2.Environment:
        if self._jinja_env is None:
            self.reload()
        assert self._jinja_env is not None
        return self._jinja_env

    def list_templates(self) -> List[TemplateMetadata]:
        """Return all discovered templates."""
        return list(self._templates_cache.values())

    def get_template_metadata(self, name: str) -> Optional[TemplateMetadata]:
        """Retrieve metadata for a specific template name."""
        return self._templates_cache.get(name)

    def get_template_source(self, name: str) -> Optional[str]:
        """Return raw Jinja2 source string for a template."""
        return self._template_sources.get(name)

    def get_defaults(self, name: str) -> Dict[str, Any]:
        """Extract default values defined in the template schema."""
        meta = self.get_template_metadata(name)
        if not meta:
            return {}
        defaults = {}
        for param_name, details in meta.parameters.items():
            if isinstance(details, dict) and "default" in details:
                defaults[param_name] = details["default"]
        return defaults
