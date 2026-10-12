from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_orchestrator import __version__
from workflow_orchestrator.doctor import run_doctor


def main() -> None:
    parser = argparse.ArgumentParser(prog="workflow", description="OpenSpec Workflow Orchestrator compatibility spike")
    parser.add_argument("--version", action="version", version=f"workflow {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor", help="Inspect local repository and CLI compatibility")
    doctor.add_argument("--repo", type=Path, default=Path.cwd())
    doctor.add_argument("--change", required=True, help="Existing OpenSpec change ID")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable report (default output is JSON for this spike)")
    args = parser.parse_args()
    if args.command == "doctor":
        report = run_doctor(args.repo, args.change)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        raise SystemExit(0 if report["overall_ok"] else 1)


if __name__ == "__main__":
    main()
