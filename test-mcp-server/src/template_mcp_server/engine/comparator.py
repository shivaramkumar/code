"""Text and model comparator for detecting drift and structural differences."""

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

from ..models.schemas import ComparisonResult
from .audit import AuditManager
from ..templates.registry import TemplateRegistry


class FieldExtractor:
    """Extracts field values from various text formats (YAML, JSON, Python, Key-Value)."""

    @classmethod
    def extract(cls, content: str, file_type: str = "auto") -> Dict[str, Any]:
        """Extract key-value fields from content based on file type."""
        stripped = content.strip()
        if not stripped:
            return {}

        if file_type == "auto":
            file_type = cls._detect_type(content)

        if file_type in ("yaml", "yml"):
            return cls._extract_yaml(content)
        elif file_type == "json":
            return cls._extract_json(content)
        elif file_type in ("python", "py"):
            return cls._extract_python(content)
        elif file_type in ("markdown", "md"):
            return cls._extract_markdown(content)
        else:
            return cls._extract_key_value(content)

    @classmethod
    def _detect_type(cls, content: str) -> str:
        """Heuristically detect content type."""
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return "json"
        if stripped.startswith("---") or ("\napp:" in content or "\nserver:" in content):
            return "yaml"
        if ("def " in content or "import " in content or "class " in content or "=" in content) and (
            ":" in content and "\n" in content
        ):
            # Check if valid python ast
            try:
                ast.parse(content)
                return "python"
            except Exception:
                pass
        return "yaml"

    @classmethod
    def _extract_yaml(cls, content: str) -> Dict[str, Any]:
        """Extract fields from YAML, flattening top-level and 1-level nested dicts."""
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return {}
            flattened = {}
            for k, v in data.items():
                flattened[str(k)] = v
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        flattened[f"{sub_k}"] = sub_v
                        flattened[f"{k}.{sub_k}"] = sub_v
                        flattened[f"{k}_{sub_k}"] = sub_v
            return flattened
        except Exception:
            return cls._extract_key_value(content)

    @classmethod
    def _extract_json(cls, content: str) -> Dict[str, Any]:
        """Extract fields from JSON."""
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                flattened = {}
                for k, v in data.items():
                    flattened[str(k)] = v
                    if isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            flattened[f"{sub_k}"] = sub_v
                            flattened[f"{k}.{sub_k}"] = sub_v
                            flattened[f"{k}_{sub_k}"] = sub_v
                return flattened
            return {}
        except Exception:
            return {}

    @classmethod
    def _extract_python(cls, content: str) -> Dict[str, Any]:
        """Extract top-level variable assignments from Python source."""
        fields: Dict[str, Any] = {}
        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            val = cls._ast_to_value(node.value)
                            fields[target.id.lower()] = val
                            fields[target.id] = val
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name) and node.value:
                        val = cls._ast_to_value(node.value)
                        fields[node.target.id.lower()] = val
                        fields[node.target.id] = val
        except Exception:
            # Fallback to regex assignments
            for match in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", content, re.MULTILINE):
                key = match.group(1).strip()
                val_str = match.group(2).strip().strip("\"'")
                fields[key.lower()] = val_str
                fields[key] = val_str
        return fields

    @classmethod
    def _ast_to_value(cls, node: ast.AST) -> Any:
        """Convert AST literal or constant node to Python object."""
        try:
            return ast.literal_eval(node)
        except Exception:
            return ast.unparse(node) if hasattr(ast, "unparse") else str(node)

    @classmethod
    def _extract_markdown(cls, content: str) -> Dict[str, Any]:
        """Extract frontmatter or heading fields from markdown."""
        fields: Dict[str, Any] = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fields.update(cls._extract_yaml(parts[1]))

        # Also extract title from top '# Title'
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            fields["title"] = title_match.group(1).strip()

        # Extract author from '## Author\n...'
        author_match = re.search(r"##\s+Author\s*\n+([^\n#]+)", content, re.MULTILINE)
        if author_match:
            fields["author"] = author_match.group(1).strip()

        # Extract description
        desc_match = re.search(r"^#\s+[^\n]+\n+([^\n#]+)", content, re.MULTILINE)
        if desc_match:
            fields["description"] = desc_match.group(1).strip()

        return fields

    @classmethod
    def _extract_key_value(cls, content: str) -> Dict[str, Any]:
        """Extract standard KEY=VALUE or KEY: VALUE lines."""
        fields: Dict[str, Any] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                fields[k.strip().lower()] = v.strip().strip("\"'")
            elif ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip().lower()] = v.strip().strip("\"'")
        return fields


class TextComparator:
    """Compares current workspace text against server models/templates."""

    def __init__(self, registry: TemplateRegistry):
        self.registry = registry

    def compare_with_template(
        self,
        template_name: str,
        current_text: str,
        model_data: Optional[Dict[str, Any]] = None,
    ) -> ComparisonResult:
        """Compare client text with template model, returning diff and field drift."""
        meta = self.registry.get_template_metadata(template_name)
        if not meta:
            raise ValueError(f"Template '{template_name}' not found.")

        # Extract client fields
        client_fields = FieldExtractor.extract(current_text, meta.file_type)

        # Base model values to compare against
        schema_defaults = self.registry.get_defaults(template_name)
        expected_model = {**schema_defaults, **(model_data or {})}

        # Identify field drift
        added_fields: Dict[str, Any] = {}
        removed_fields: Dict[str, Any] = {}
        modified_fields: Dict[str, Dict[str, Any]] = {}
        retained_fields: Dict[str, Any] = {}

        help_text_drift = None

        # Common alias mappings for instances (sensor, actor, device)
        alias_map = {
            "instance_name": ["id", "instance.id", "name", "instance.name", "instance_id"],
            "sensor_type": ["type", "instance.type", "sensor_model"],
            "actor_type": ["type", "instance.type", "actuator_type"],
            "help_text": ["instance.help_text", "description", "instance.description", "doc", "help"],
            "pin_channel": ["hardware.pin_channel", "pin", "channel"],
            "sampling_rate_hz": ["hardware.sampling_rate_hz", "rate"],
            "max_current_ma": ["hardware.max_current_ma"],
            "safety_limit": ["safety.safety_limit"],
            "unit": ["measurement.unit"],
        }

        for key, expected_val in expected_model.items():
            candidates = [key, key.lower(), key.replace("_", "."), key.replace(".", "_")]
            if key in alias_map:
                candidates.extend(alias_map[key])
            matching_key = next((c for c in candidates if c in client_fields), None)
            if matching_key is None:
                added_fields[key] = expected_val
            else:
                client_val = client_fields[matching_key]
                if str(client_val).strip() == str(expected_val).strip():
                    retained_fields[key] = client_val
                else:
                    modified_fields[key] = {
                        "client_value": client_val,
                        "model_value": expected_val,
                    }
                    if "help" in key.lower():
                        help_text_drift = {
                            "client_help_text": str(client_val),
                            "model_help_text": str(expected_val),
                        }

        for k, v in client_fields.items():
            k_candidates = [k, k.lower(), k.replace("_", "."), k.replace(".", "_")]
            is_matched = False
            for cand in k_candidates:
                if cand in expected_model:
                    is_matched = True
                    break
                for param_key, aliases in alias_map.items():
                    if cand in aliases and param_key in expected_model:
                        is_matched = True
                        break
                if is_matched:
                    break
            if not is_matched:
                removed_fields[k] = v

        # Render expected template with merged client fields or expected model
        rendered_model = self._render_template(template_name, expected_model)
        diff = AuditManager.compute_diff(
            current_text,
            rendered_model,
            fromfile="client_workspace",
            tofile=f"template_{template_name}",
        )

        identical = (current_text.strip() == rendered_model.strip())
        if identical:
            drift_detected = False
            added_fields = {}
            removed_fields = {}
            modified_fields = {}
            retained_fields = dict(expected_model)
            help_text_drift = None
        else:
            drift_detected = bool(added_fields or removed_fields or modified_fields or diff.strip())

        summary_parts = []
        if identical:
            summary_parts.append("Workspace text is identical to server template.")
        else:
            if help_text_drift:
                summary_parts.append("Help text drift detected in instance documentation")
            if added_fields:
                summary_parts.append(f"Added model fields: {list(added_fields.keys())}")
            if removed_fields:
                summary_parts.append(f"Custom/extra workspace fields: {list(removed_fields.keys())}")
            if modified_fields:
                summary_parts.append(f"Modified field values: {list(modified_fields.keys())}")
            if not summary_parts:
                summary_parts.append("Text formatting or structural difference detected.")

        return ComparisonResult(
            identical=identical,
            drift_detected=drift_detected,
            added_fields=added_fields,
            removed_fields=removed_fields,
            modified_fields=modified_fields,
            retained_fields=retained_fields,
            help_text_drift=help_text_drift,
            unified_diff=diff,
            summary="; ".join(summary_parts),
        )

    def compare_file(
        self,
        file_path: str,
        template_name: str,
        model_data: Optional[Dict[str, Any]] = None,
        current_content: Optional[str] = None,
    ) -> ComparisonResult:
        """Compare client workspace file against template. Accepts `current_content` directly for remote execution."""
        if current_content is not None:
            content = current_content
        else:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Workspace file '{file_path}' does not exist and no current_content was provided.")
            content = path.read_text(encoding="utf-8")
        return self.compare_with_template(template_name, content, model_data)

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        source = self.registry.get_template_source(template_name)
        if not source:
            return ""
        template = self.registry.jinja_env.from_string(source)
        return template.render(**context)
