# OpenSpec Workflow Orchestrator — Compatibility Spike

A small, dependency-free Python prototype for the first implementation step. It is designed to be run against a local project without changing that project.

## What is implemented

- `workflow doctor --repo PATH --change CHANGE_ID`: checks Git, locates OpenSpec/GigaCode CLIs, captures a Git baseline, and probes OpenSpec status/validation.
- OpenSpec adapter using documented command shapes: `openspec status --change <id> --json` and `openspec validate <id> --no-interactive`.
- GigaCode adapter with configurable argv, JSON parsing for `session_id`, `stop_reason`, and `is_error`, timeout/error capture.
- Git snapshot adapter for `HEAD` and porcelain worktree status.
- Unit tests using mocked external processes; no Java repo, OpenSpec install, or GigaCode install is needed to run tests.

## What is deliberately not claimed yet

- The GigaCode invocation syntax is not validated against a live installed CLI. The default `gigacode --output-format json <prompt>` is configurable and must be confirmed locally.
- The adapter does not yet implement session resume (`--resume <session_id>`), workflow state persistence, or recovery policy. Those belong after the compatibility probe.
- `openspec validate` output varies by installed version; the spike treats its exit code as the primary signal.
- This is not the full orchestrator MVP yet.

## Setup

Python 3.11+ is recommended. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

No third-party runtime dependencies are required.

## Run the compatibility probe

```bash
workflow doctor --repo /path/to/your/project --change your-existing-change-id
```

Or without installation:

```bash
PYTHONPATH=src python -m workflow_orchestrator.cli doctor --repo /path/to/your/project --change your-existing-change-id
```

The command is read-only with respect to project files. OpenSpec may emit diagnostics to stdout/stderr; the probe does not invoke GigaCode to edit files.

## Design notes from the reference audit

The reference `spec-orchestrate` is a thin state-machine conductor and delegates actual work. Its full flow includes intake, spec generation/review, approval, implementation, acceptance evaluation, PR, and retrospective. This project intentionally narrows the scope to an already-existing OpenSpec change, implementation through GigaCode, observable verification, and safe resume. We should reuse patterns, not port the full Issue-to-PR pipeline wholesale.

Reference: https://github.com/anyoneanderson/agent-skills
OpenSpec CLI reference: https://openspec.dev/docs/cli
