from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from workflow_orchestrator import __version__
from workflow_orchestrator.doctor import run_doctor
from workflow_orchestrator.workflow_service import (
    WorkflowCommandError,
    get_workflow_status,
    start_workflow,
)


def _add_repo_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(),
        help="Target Git repository (default: current directory)",
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="Local OpenSpec Workflow Orchestrator",
    )
    parser.add_argument("--version", action="version", version=f"workflow {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Inspect local repository and CLI compatibility")
    _add_repo_argument(doctor)
    doctor.add_argument("--change", required=True, help="Existing OpenSpec change ID")
    doctor.add_argument("--json", action="store_true", help="Retained for compatibility; output is JSON")

    start = subparsers.add_parser("start", help="Create a persisted workflow run (state initialization only in this version)")
    start.add_argument("change_id", help="Existing OpenSpec change ID")
    _add_repo_argument(start)
    start.add_argument("--max-attempts", type=int, default=2, help="Retry limit to store for this run (default: 2)")

    status = subparsers.add_parser("status", help="Show the persisted status of a workflow run")
    status.add_argument("change_id", nargs="?", help="OpenSpec change ID; omitted when exactly one run exists")
    _add_repo_argument(status)
    status.add_argument("--events", action="store_true", help="Include the complete event log")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        report = run_doctor(args.repo, args.change)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        raise SystemExit(0 if report["overall_ok"] else 1)

    try:
        if args.command == "start":
            report = start_workflow(args.repo, args.change_id, max_attempts=args.max_attempts)
        elif args.command == "status":
            report = get_workflow_status(args.repo, args.change_id, include_events=args.events)
        else:  # Defensive; argparse requires a known command.
            parser.error(f"Unsupported command: {args.command}")
            return
    except (WorkflowCommandError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        raise SystemExit(1) from exc

    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
