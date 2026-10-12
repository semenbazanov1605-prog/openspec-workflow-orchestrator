"""Atomic JSON persistence and append-only event log for workflow state."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from workflow_orchestrator.models import WorkflowState


_CHANGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StateStoreError(RuntimeError):
    """Raised when workflow state cannot be safely loaded or persisted."""


class StateStore:
    """Persist workflow runs under ``<repo>/.workflow/runs/<change-id>/``."""

    def __init__(self, repository_root: Path):
        self.repository_root = repository_root.expanduser().resolve()
        self.runs_root = self.repository_root / ".workflow" / "runs"

    def run_dir(self, change_id: str) -> Path:
        self._validate_change_id(change_id)
        return self.runs_root / change_id

    def state_path(self, change_id: str) -> Path:
        return self.run_dir(change_id) / "state.json"

    def events_path(self, change_id: str) -> Path:
        return self.run_dir(change_id) / "events.jsonl"

    def create(self, state: WorkflowState) -> None:
        """Create a run; refuse to overwrite a previously saved state."""
        path = self.state_path(state.change_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise StateStoreError(
                f"Workflow state already exists for change '{state.change_id}'. "
                "Load or explicitly archive the existing run before creating another."
            )
        self._atomic_write_state(path, state)
        self.append_event(
            state.change_id,
            "run_created",
            run_id=state.run_id,
            details={"status": state.status.value, "phase": state.phase.value},
        )

    def load(self, change_id: str) -> WorkflowState:
        """Load and schema-validate one workflow state."""
        path = self.state_path(change_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise StateStoreError(f"No saved workflow state for change '{change_id}'") from exc
        except OSError as exc:
            raise StateStoreError(f"Cannot read workflow state at {path}: {exc}") from exc
        try:
            state = WorkflowState.from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StateStoreError(f"Invalid workflow state at {path}: {exc}") from exc
        if state.change_id != change_id:
            raise StateStoreError(
                f"State change_id mismatch: requested '{change_id}', file contains '{state.change_id}'"
            )
        return state

    def save(
        self,
        state: WorkflowState,
        *,
        event_type: str = "state_saved",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Atomically replace the state file, then append a journal event."""
        path = self.state_path(state.change_id)
        if not path.exists():
            raise StateStoreError(
                f"Cannot update missing workflow state for change '{state.change_id}'; use create() first"
            )
        self._atomic_write_state(path, state)
        event_details: dict[str, Any] = {
            "status": state.status.value,
            "phase": state.phase.value,
        }
        if details:
            event_details.update(dict(details))
        self.append_event(state.change_id, event_type, run_id=state.run_id, details=event_details)

    def append_event(
        self,
        change_id: str,
        event_type: str,
        *,
        run_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Append one JSON event to the per-change JSONL journal."""
        if not event_type or not event_type.strip():
            raise ValueError("event_type must not be empty")
        path = self.events_path(change_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "event_type": event_type,
            "change_id": change_id,
            "run_id": run_id,
            "details": dict(details or {}),
        }
        encoded = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        try:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise StateStoreError(f"Cannot append workflow event to {path}: {exc}") from exc

    def read_events(self, change_id: str) -> list[dict[str, Any]]:
        """Read the event journal in append order."""
        path = self.events_path(change_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise StateStoreError(
                            f"Invalid event JSON at {path}:{line_number}: {exc}"
                        ) from exc
                    if not isinstance(event, dict):
                        raise StateStoreError(
                            f"Invalid event at {path}:{line_number}: expected a JSON object"
                        )
                    events.append(event)
        except OSError as exc:
            raise StateStoreError(f"Cannot read workflow events at {path}: {exc}") from exc
        return events

    def list_changes(self) -> list[str]:
        """Return change IDs that have a persisted state file."""
        if not self.runs_root.exists():
            return []
        changes: list[str] = []
        try:
            for candidate in self.runs_root.iterdir():
                if not candidate.is_dir() or not (candidate / "state.json").is_file():
                    continue
                try:
                    self._validate_change_id(candidate.name)
                except ValueError:
                    continue
                changes.append(candidate.name)
        except OSError as exc:
            raise StateStoreError(f"Cannot list workflow runs under {self.runs_root}: {exc}") from exc
        return sorted(changes)

    def _atomic_write_state(self, path: Path, state: WorkflowState) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        temp_path: Path | None = None
        try:
            file_descriptor, temp_name = tempfile.mkstemp(
                prefix=".state-", suffix=".tmp", dir=path.parent
            )
            temp_path = Path(temp_name)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
            # Persist the directory entry where the platform supports it.
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        except OSError as exc:
            raise StateStoreError(f"Cannot persist workflow state at {path}: {exc}") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _validate_change_id(change_id: str) -> None:
        if not isinstance(change_id, str) or not _CHANGE_ID_RE.fullmatch(change_id):
            raise ValueError(
                "Invalid change ID: use 1-128 letters, digits, dots, underscores or hyphens; "
                "the first character must be a letter or digit"
            )
