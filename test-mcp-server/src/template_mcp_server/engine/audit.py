from collections.abc import Awaitable, Callable
import difflib
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from ..models.schemas import AuditAction, AuditEntry

logger = logging.getLogger(__name__)


class AuditManager:
    """Manages audit records and file snapshots to track changes made at client side."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.audit_dir = Path(base_dir)
        elif os.environ.get("MCP_AUDIT_DIR"):
            self.audit_dir = Path(os.environ["MCP_AUDIT_DIR"])
        else:
            self.audit_dir = Path.cwd() / ".mcp_audit"

        self.snapshots_dir = self.audit_dir / "snapshots"
        self.log_file = self.audit_dir / "audit_log.jsonl"
        self._known_client_dirs: set[Path] = set()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create audit directories if they don't exist."""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_diff(old_content: str, new_content: str, fromfile: str = "before", tofile: str = "after") -> str:
        """Compute unified diff between old and new content."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=fromfile,
            tofile=tofile,
        )
        return "".join(diff)

    @staticmethod
    def get_client_audit_dir(file_path: Path) -> Optional[Path]:
        """Find the client workspace root and return its .mcp_audit directory."""
        try:
            curr = file_path.resolve().parent if not file_path.is_dir() else file_path.resolve()
            for parent in [curr, *curr.parents]:
                if (parent / ".mcp_audit").exists():
                    return parent / ".mcp_audit"
                if (parent / ".mcp-audit").exists():
                    return parent / ".mcp-audit"
                if (parent / ".git").exists() or (parent / ".vscode").exists():
                    return parent / ".mcp_audit"
                if (parent / "pyproject.toml").exists() or (parent / "package.json").exists():
                    return parent / ".mcp_audit"
            return curr / ".mcp_audit"
        except Exception:
            return None

    def create_snapshot(
        self,
        file_path: Path,
        content: str,
        client_audit_dir: Optional[Path] = None,
        write_client_disk: bool = True,
    ) -> str:
        """Save a snapshot of content for rollback tracking in both server and client audit directories."""
        self._ensure_dirs()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        content_hash = self._compute_hash(content)[:8]
        safe_name = file_path.name.replace("/", "_")
        snapshot_filename = f"{timestamp}_{content_hash}_{safe_name}"

        # 1. Save in server audit directory (always)
        server_snapshot_path = self.snapshots_dir / snapshot_filename
        server_snapshot_path.write_text(content, encoding="utf-8")

        # 2. Save in client workspace audit directory (only in local co-located mode)
        if write_client_disk and client_audit_dir and client_audit_dir.resolve() != self.audit_dir.resolve():
            try:
                client_snapshots = client_audit_dir / "snapshots"
                client_snapshots.mkdir(parents=True, exist_ok=True)
                (client_snapshots / snapshot_filename).write_text(content, encoding="utf-8")
            except Exception as e:
                logger.warning("Could not write client snapshot to %s: %s", client_audit_dir, e)

        return str(server_snapshot_path)

    @staticmethod
    def _write_entry_to_log(log_path: Path, entry: AuditEntry) -> None:
        """Write audit entry to specified log file as a JSONL line."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    @staticmethod
    def _read_entries_from_log(log_path: Path) -> List[AuditEntry]:
        """Read audit entries from a log file (supports both JSONL and JSON array)."""
        if not log_path.exists():
            return []

        content = log_path.read_text(encoding="utf-8").strip()
        if not content:
            return []

        raw_items: List[Dict[str, Any]] = []
        if content.startswith("["):
            try:
                raw_items = json.loads(content)
            except Exception:
                pass

        if not raw_items:
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_items.append(json.loads(line))
                except Exception:
                    continue

        entries: List[AuditEntry] = []
        for data in raw_items:
            try:
                entries.append(AuditEntry(**data))
            except Exception:
                continue
        return entries

    def record_action(
        self,
        action: AuditAction,
        file_path: str,
        previous_content: Optional[str],
        new_content: str,
        template_name: Optional[str] = None,
        git_commit: Optional[str] = None,
        git_remote: Optional[str] = None,
        retained_fields: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        write_client_disk: bool = True,
    ) -> AuditEntry:
        """Record an audit entry in both server and client workspace audit directories."""
        self._ensure_dirs()
        entry_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        target = Path(file_path)
        prev_hash = self._compute_hash(previous_content) if previous_content is not None else None
        new_hash = self._compute_hash(new_content) if new_content is not None else None

        # Resolve client workspace audit directory
        client_audit_dir = self.get_client_audit_dir(target)
        if client_audit_dir:
            self._known_client_dirs.add(client_audit_dir.resolve())

        snapshot_path = None
        client_snapshot_path = None
        if previous_content is not None:
            snapshot_path = self.create_snapshot(
                target,
                previous_content,
                client_audit_dir=client_audit_dir,
                write_client_disk=write_client_disk,
            )
            if client_audit_dir and client_audit_dir.resolve() != self.audit_dir.resolve():
                timestamp_name = Path(snapshot_path).name
                client_snapshot_path = str(client_audit_dir / "snapshots" / timestamp_name)

        diff = self.compute_diff(
            previous_content if previous_content is not None else "",
            new_content if new_content is not None else "",
            fromfile=f"a/{target.name}",
            tofile=f"b/{target.name}",
        )

        entry_metadata = dict(metadata or {})
        if client_audit_dir:
            entry_metadata["client_audit_dir"] = str(client_audit_dir)
        if client_snapshot_path:
            entry_metadata["client_snapshot_path"] = str(client_snapshot_path)

        entry = AuditEntry(
            id=entry_id,
            timestamp=now_iso,
            action=action,
            file_path=str(target.resolve() if target.is_absolute() else target),
            template_name=template_name,
            git_commit=git_commit,
            git_remote=git_remote,
            previous_hash=prev_hash,
            new_hash=new_hash,
            diff=diff,
            snapshot_path=snapshot_path,
            retained_fields=retained_fields,
            metadata=entry_metadata,
        )

        # 1. Write to central server log (.jsonl only)
        self._write_entry_to_log(self.log_file, entry)

        # 2. Write to client workspace audit log (.jsonl only) in local co-located mode
        if write_client_disk and client_audit_dir and client_audit_dir.resolve() != self.audit_dir.resolve():
            try:
                client_audit_dir.mkdir(parents=True, exist_ok=True)
                self._write_entry_to_log(client_audit_dir / "audit_log.jsonl", entry)
            except Exception as e:
                logger.warning("Could not write client audit log to %s: %s", client_audit_dir, e)

        return entry

    def create_audit_bundle(
        self,
        action: AuditAction,
        file_path: str,
        previous_content: Optional[str],
        new_content: str,
        template_name: Optional[str] = None,
        git_commit: Optional[str] = None,
        git_remote: Optional[str] = None,
        retained_fields: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        write_client_disk: bool = False,
    ) -> Dict[str, Any]:
        """Record audit action on server and compute client-side audit resource paths and payloads."""
        entry = self.record_action(
            action=action,
            file_path=file_path,
            previous_content=previous_content,
            new_content=new_content,
            template_name=template_name,
            git_commit=git_commit,
            git_remote=git_remote,
            retained_fields=retained_fields,
            metadata=metadata,
            write_client_disk=write_client_disk,
        )

        p = Path(file_path)
        if p.is_absolute():
            client_dir = self.get_client_audit_dir(p)
            audit_log_path = str((client_dir / "audit_log.jsonl") if client_dir else (p.parent / ".mcp_audit" / "audit_log.jsonl"))
            snapshots_dir = str((client_dir / "snapshots") if client_dir else (p.parent / ".mcp_audit" / "snapshots"))
        else:
            audit_log_path = ".mcp_audit/audit_log.jsonl"
            snapshots_dir = ".mcp_audit/snapshots"

        snapshot_filename = Path(entry.snapshot_path).name if entry.snapshot_path else None
        snapshot_path = f"{snapshots_dir}/{snapshot_filename}" if (snapshot_filename and previous_content is not None) else None

        return {
            "entry": entry,
            "audit_id": entry.id,
            "audit_log_path": audit_log_path,
            "audit_log_text": entry.model_dump_json() + "\n",
            "snapshot_path": snapshot_path,
            "snapshot_filename": snapshot_filename,
            "snapshot_text": previous_content,
        }

    def get_snapshot_content(self, entry_id: str, file_path: Optional[str] = None) -> Optional[str]:
        """Retrieve the snapshot content associated with an audit entry."""
        entry = self.get_entry(entry_id, file_path=file_path)
        if not entry:
            return None

        if entry.snapshot_path and os.path.exists(entry.snapshot_path):
            try:
                return Path(entry.snapshot_path).read_text(encoding="utf-8")
            except Exception:
                pass

        if entry.metadata.get("client_snapshot_path") and os.path.exists(entry.metadata["client_snapshot_path"]):
            try:
                return Path(entry.metadata["client_snapshot_path"]).read_text(encoding="utf-8")
            except Exception:
                pass

        if entry.snapshot_path:
            filename = Path(entry.snapshot_path).name
            target = Path(entry.file_path)
            client_dir = self.get_client_audit_dir(target)
            if client_dir and (client_dir / "snapshots" / filename).exists():
                try:
                    return (client_dir / "snapshots" / filename).read_text(encoding="utf-8")
                except Exception:
                    pass
            if (self.snapshots_dir / filename).exists():
                try:
                    return (self.snapshots_dir / filename).read_text(encoding="utf-8")
                except Exception:
                    pass

        return None

    def get_audit_trail(self, file_path: Optional[str] = None, limit: int = 50) -> List[AuditEntry]:
        """Retrieve audit history, checking client workspace audit log first if file_path is given."""
        target_filter = str(Path(file_path).resolve()) if file_path else None
        client_dir = self.get_client_audit_dir(Path(file_path)) if file_path else None

        # Collect candidate log files: client workspace log first, then known client dirs, then cwd, then server log
        log_files: List[Path] = []
        if client_dir:
            for fname in ["audit_log.json", "audit_log.jsonl"]:
                candidate = client_dir / fname
                if candidate.exists() and candidate not in log_files:
                    log_files.append(candidate)

        for known_dir in self._known_client_dirs:
            for fname in ["audit_log.json", "audit_log.jsonl"]:
                candidate = known_dir / fname
                if candidate.exists() and candidate not in log_files:
                    log_files.append(candidate)

        for cwd_name in [".mcp_audit", ".mcp-audit"]:
            cwd_dir = Path.cwd() / cwd_name
            if cwd_dir.exists():
                for fname in ["audit_log.json", "audit_log.jsonl"]:
                    candidate = cwd_dir / fname
                    if candidate.exists() and candidate not in log_files:
                        log_files.append(candidate)

        if self.log_file.exists() and self.log_file.resolve() not in [p.resolve() for p in log_files]:
            log_files.append(self.log_file)
        server_json = self.audit_dir / "audit_log.json"
        if server_json.exists() and server_json.resolve() not in [p.resolve() for p in log_files]:
            log_files.append(server_json)

        entries_by_id: Dict[str, AuditEntry] = {}
        for log_file in log_files:
            for entry in self._read_entries_from_log(log_file):
                if target_filter:
                    entry_resolved = str(Path(entry.file_path).resolve())
                    if entry_resolved != target_filter and entry.file_path != file_path:
                        continue
                if entry.id not in entries_by_id:
                    entries_by_id[entry.id] = entry

        # Sort by timestamp descending
        sorted_entries = sorted(entries_by_id.values(), key=lambda e: e.timestamp, reverse=True)
        return sorted_entries[:limit]

    def get_entry(self, entry_id: str, file_path: Optional[str] = None) -> Optional[AuditEntry]:
        """Fetch single audit record by entry id, searching client workspace log if file_path is given."""
        if file_path:
            for entry in self.get_audit_trail(file_path=file_path, limit=1000):
                if entry.id == entry_id:
                    return entry
        for entry in self.get_audit_trail(limit=1000):
            if entry.id == entry_id:
                return entry
        return None

    def rollback(self, entry_id: str, file_path: Optional[str] = None) -> Tuple[bool, str]:
        """Roll back a specific change by restoring its snapshot or removing file if it was created new."""
        entry = self.get_entry(entry_id, file_path=file_path)
        if not entry:
            return False, f"Audit entry '{entry_id}' not found."

        target = Path(entry.file_path)
        current_content = target.read_text(encoding="utf-8") if target.exists() else None

        # Resolve snapshot location:
        # 1. Stored snapshot path on server (if still valid)
        # 2. Client snapshot path from entry metadata
        # 3. Client workspace snapshots dir
        # 4. Server snapshots dir
        snapshot_path: Optional[Path] = None
        if entry.snapshot_path and os.path.exists(entry.snapshot_path):
            snapshot_path = Path(entry.snapshot_path)
        elif entry.metadata.get("client_snapshot_path") and os.path.exists(entry.metadata["client_snapshot_path"]):
            snapshot_path = Path(entry.metadata["client_snapshot_path"])
        elif entry.snapshot_path:
            filename = Path(entry.snapshot_path).name
            client_dir = self.get_client_audit_dir(target)
            if client_dir and (client_dir / "snapshots" / filename).exists():
                snapshot_path = client_dir / "snapshots" / filename
            elif (self.snapshots_dir / filename).exists():
                snapshot_path = self.snapshots_dir / filename

        if snapshot_path and snapshot_path.exists():
            restored_content = snapshot_path.read_text(encoding="utf-8")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(restored_content, encoding="utf-8")
            except Exception as e:
                logger.warning("Could not write restored content to %s on server: %s", target, e)

            # Log rollback action
            self.record_action(
                action=AuditAction.ROLLBACK,
                file_path=str(target),
                previous_content=current_content,
                new_content=restored_content,
                template_name=entry.template_name,
                metadata={"rolled_back_entry_id": entry.id},
            )
            return True, f"Successfully rolled back {entry.file_path} to snapshot prior to {entry.id}."
        elif entry.previous_hash is None:
            # File did not exist before this entry was generated; delete it
            if target.exists():
                try:
                    target.unlink()
                except Exception as e:
                    logger.warning("Could not remove %s on server: %s", target, e)
            self.record_action(
                action=AuditAction.ROLLBACK,
                file_path=str(target),
                previous_content=current_content,
                new_content="",
                template_name=entry.template_name,
                metadata={"rolled_back_entry_id": entry.id, "action_taken": "file_deleted"},
            )
            return True, f"Successfully rolled back by removing {entry.file_path} (it was newly created in {entry.id})."
        else:
            return False, f"Snapshot not found for entry '{entry_id}', cannot reliably restore."

    def expand_audit_log(
        self,
        file_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Expand and format audit_log.jsonl into an indented JSON file on demand.

        Args:
            file_path: Optional path to a file or directory in the target workspace.
                       If provided, expands that workspace's audit log; otherwise expands the server audit log.
            output_path: Optional custom path for the generated JSON file. Defaults to 'audit_log.json' in the same audit directory.

        Returns:
            Tuple of (success, message, json_file_path).
        """
        target_dir: Optional[Path] = None
        if file_path:
            p = Path(file_path)
            target_dir = self.get_client_audit_dir(p)
            if not target_dir or not (target_dir / "audit_log.jsonl").exists():
                if p.is_dir() and (p / "audit_log.jsonl").exists():
                    target_dir = p
                elif p.is_file() and p.name.endswith(".jsonl"):
                    target_dir = p.parent

        if not target_dir or not (target_dir / "audit_log.jsonl").exists():
            target_dir = self.audit_dir

        src_jsonl = target_dir / "audit_log.jsonl"
        if not src_jsonl.exists():
            return False, f"No audit_log.jsonl found in {target_dir}.", None

        entries = self._read_entries_from_log(src_jsonl)
        if not entries:
            return False, f"Audit log {src_jsonl} is empty.", None

        dest_json = Path(output_path) if output_path else target_dir / "audit_log.json"
        dest_json.parent.mkdir(parents=True, exist_ok=True)

        json_data = [json.loads(e.model_dump_json()) for e in entries]
        dest_json.write_text(json.dumps(json_data, indent=2) + "\n", encoding="utf-8")

        return True, f"Successfully expanded {len(entries)} audit entries to {dest_json}.", str(dest_json)

    # ==========================================
    # MCP SERVER MIDDLEWARE (OBSERVABILITY)
    # ==========================================

    @property
    def middleware(self) -> "AuditManager":
        """Return self for use in mcp.middleware.append(audit_manager.middleware)."""
        return self

    def as_middleware(self) -> "AuditManager":
        """Return self for use as an MCP ServerMiddleware."""
        return self

    async def __call__(
        self,
        ctx: Any,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Observe and log inbound requests and tool calls (provisional middleware)."""
        start = time.perf_counter()
        method = getattr(ctx, "method", "unknown")
        params = getattr(ctx, "params", None)
        tool_name = params.get("name") if isinstance(params, dict) and method == "tools/call" else getattr(params, "name", None)

        try:
            return await call_next(ctx)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "MCP request '%s'%s failed after %.1f ms: %s",
                method,
                f" (tool: {tool_name})" if tool_name else "",
                elapsed_ms,
                exc,
            )
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if tool_name:
                logger.info("Tool '%s' executed in %.1f ms", tool_name, elapsed_ms)
            else:
                logger.debug("MCP request '%s' completed in %.1f ms", method, elapsed_ms)
