"""Migration engine for upgrading workspace files to latest templates while retaining field values and help texts."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..models.schemas import AuditAction, MigrationResult
from .audit import AuditManager
from .comparator import FieldExtractor
from .generator import TemplateGenerator
from ..templates.registry import TemplateRegistry

logger = logging.getLogger(__name__)


class TemplateMigrator:
    """Migrates existing files in client workspace to latest template versions while retaining custom field values and help texts."""

    def __init__(
        self,
        registry: TemplateRegistry,
        generator: TemplateGenerator,
        audit_manager: Optional[AuditManager] = None,
    ):
        self.registry = registry
        self.generator = generator
        self.audit_manager = audit_manager or AuditManager()

    def migrate_file(
        self,
        file_path: str,
        template_name: str,
        extra_updates: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        current_content: Optional[str] = None,
    ) -> MigrationResult:
        """Migrate a workspace file to latest template version, preserving existing fields and help texts."""
        path = Path(file_path)
        if current_content is not None:
            current_text = current_content
        else:
            if not path.exists():
                return MigrationResult(
                    success=False,
                    file_path=file_path,
                    template_name=template_name,
                    message=f"File '{file_path}' does not exist and no current_content was provided.",
                )
            current_text = path.read_text(encoding="utf-8")
        meta = self.registry.get_template_metadata(template_name)
        if not meta:
            return MigrationResult(
                success=False,
                file_path=file_path,
                template_name=template_name,
                message=f"Template '{template_name}' not found.",
            )

        # 1. Extract existing fields from client space
        extracted_fields = FieldExtractor.extract(current_text, meta.file_type)

        # 2. Get defaults from latest template
        template_defaults = self.registry.get_defaults(template_name)

        # 3. Match extracted fields against template parameters (supporting instance aliases)
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

        retained_fields: Dict[str, Any] = {}
        retained_help_texts: Dict[str, Any] = {}
        new_fields_applied: Dict[str, Any] = {}

        merged_context: Dict[str, Any] = dict(template_defaults)

        # Retain client field values
        for param_name in meta.parameters.keys():
            candidates = [param_name, param_name.lower(), param_name.replace("_", "."), param_name.replace(".", "_")]
            if param_name in alias_map:
                candidates.extend(alias_map[param_name])

            matching_key = next((c for c in candidates if c in extracted_fields), None)

            if matching_key is not None:
                client_value = extracted_fields[matching_key]
                merged_context[param_name] = client_value
                retained_fields[param_name] = client_value
                if "help" in param_name.lower() or "desc" in param_name.lower():
                    retained_help_texts[param_name] = client_value
            else:
                new_fields_applied[param_name] = template_defaults.get(param_name)

        # Apply any explicit extra updates requested
        if extra_updates:
            for k, v in extra_updates.items():
                merged_context[k] = v
                retained_fields[k] = v
                if "help" in k.lower():
                    retained_help_texts[k] = v

        # 4. Render latest template with merged context
        try:
            new_content = self.generator.render(template_name, merged_context)
        except Exception as e:
            return MigrationResult(
                success=False,
                file_path=file_path,
                template_name=template_name,
                message=f"Failed to render template during migration: {str(e)}",
            )

        # 5. Compute diff
        diff = AuditManager.compute_diff(
            current_text,
            new_content,
            fromfile=f"a/{path.name} (current)",
            tofile=f"b/{path.name} (migrated {template_name} v{meta.version})",
        )

        if dry_run:
            return MigrationResult(
                success=True,
                file_path=file_path,
                template_name=template_name,
                retained_fields=retained_fields,
                retained_help_texts=retained_help_texts,
                new_fields_applied=new_fields_applied,
                diff=diff,
                dry_run=True,
                new_content=new_content,
                message="Dry run migration successful. Workspace file was not modified.",
            )

        # 6. Write changes to client workspace only if running in local mode (current_content not provided)
        if current_content is None:
            try:
                path.write_text(new_content, encoding="utf-8")
            except Exception as e:
                logger.warning("Could not write migration output to %s on server: %s", path, e)

        # 7. Record in audit trail with Git submodule tracking
        sub_info = self.registry.get_submodule_info()
        audit_entry = self.audit_manager.record_action(
            action=AuditAction.MIGRATE,
            file_path=str(path),
            previous_content=current_text,
            new_content=new_content,
            template_name=template_name,
            git_commit=sub_info.get("commit_hash"),
            git_remote=sub_info.get("remote_url"),
            retained_fields=retained_fields,
            metadata={
                "template_version": meta.version,
                "retained_help_texts": retained_help_texts,
                "new_fields_applied": new_fields_applied,
            },
            write_client_disk=(current_content is None),
        )

        return MigrationResult(
            success=True,
            file_path=file_path,
            template_name=template_name,
            retained_fields=retained_fields,
            retained_help_texts=retained_help_texts,
            new_fields_applied=new_fields_applied,
            diff=diff,
            audit_id=audit_entry.id,
            dry_run=False,
            new_content=new_content,
            message=f"File successfully migrated to '{template_name}' v{meta.version}. Audit step recorded ({audit_entry.id}).",
        )
