# OpenSpec Workflow Orchestrator — Compatibility Spike

A dependency-free Python prototype for the first implementation steps. It is designed to be developed and tested locally before being run against a real Java project.

## What is implemented

- `workflow doctor --repo PATH --change CHANGE_ID`: checks Git, locates OpenSpec/GigaCode CLIs, captures a Git baseline, and probes OpenSpec status/validation.
- OpenSpec adapter using documented command shapes: `openspec status --change <id> --json` and `openspec validate <id> --no-interactive`.
- GigaCode adapter with configurable argv, JSON parsing for `session_id`, `stop_reason`, and `is_error`, timeout/error capture.
- Git snapshot adapter for `HEAD` and porcelain worktree status.
- Versioned workflow state models (`WorkflowState`, `WorkflowStatus`, `WorkflowPhase`).
- Pure state-transition rules with invalid-transition protection.
- Atomic `state.json` persistence and append-only `events.jsonl` event log under `.workflow/runs/<change-id>/`.
- Unit tests for adapters, state transitions, state persistence, malformed data, and change-ID path validation.

## What is not implemented yet

- The GigaCode invocation syntax is not validated against a live installed CLI. The default command shape is configurable and must be confirmed locally.
- Session resume (`--resume <session_id>`) is not yet wired into the adapter or workflow engine.
- The state store/state machine are not yet wired to CLI commands. There is no full `start`, `status`, `resume`, or `stop` workflow yet.
- No cross-process per-change lock exists yet; concurrent runs must not be started for the same change.
- State replacement is atomic, but writing `state.json` and appending `events.jsonl` are not one atomic transaction. State is authoritative if a crash occurs between these writes.
- This is not the full orchestrator MVP yet.

## Setup

Python 3.11+ is required. From this directory:

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

The command is read-only with respect to project source files. OpenSpec may emit diagnostics to stdout/stderr; the probe does not invoke GigaCode to edit files.

## State storage layout

For an example change ID `add-loyalty-feature`:

```text
<repository>/.workflow/runs/add-loyalty-feature/state.json
<repository>/.workflow/runs/add-loyalty-feature/events.jsonl
```

`.workflow/` is local runtime state and is ignored by Git by default. Do not commit credentials or sensitive process output to the event log.

## Design notes from the reference audit

The reference `spec-orchestrate` is a state-machine conductor and delegates actual work. Its full flow includes intake, spec generation/review, approval, implementation, acceptance evaluation, PR, and retrospective. This project intentionally narrows the scope to an already-existing OpenSpec change, implementation through GigaCode, observable verification, and safe resume. We should reuse patterns, not port the full Issue-to-PR pipeline wholesale.

Reference: https://github.com/anyoneanderson/agent-skills
OpenSpec CLI reference: https://openspec.dev/docs/cli
