# OpenSpec Workflow Orchestrator — local CLI prototype

A dependency-free Python CLI for incrementally building a safe workflow around an existing OpenSpec change and GigaCode CLI.

## Current features (v0.3.0)

- `workflow doctor --repo PATH --change CHANGE_ID`: inspect Git, OpenSpec, and GigaCode CLI availability and probe the existing OpenSpec change.
- `workflow start CHANGE_ID --repo PATH`: create a persisted initial workflow record (`READY` / `PREFLIGHT`) and capture the current Git HEAD and worktree status as a baseline.
- `workflow status [CHANGE_ID] --repo PATH`: show the saved state; if there is exactly one run, the change ID may be omitted.
- `workflow status CHANGE_ID --repo PATH --events`: include the event journal.
- Versioned state model, validated state transitions, atomic `state.json` persistence, and append-only `events.jsonl`.
- `.workflow/` runtime state is excluded through Git's local `.git/info/exclude`, not by editing the project's tracked `.gitignore`.
- Unit tests for adapters, state transitions, persistence, start/status services, and baseline behavior.

## Important limitations

This version is **not yet the complete orchestrator**:

- `workflow start` only initializes persisted state. It does not yet run OpenSpec preflight or invoke GigaCode.
- There is no `resume` or `stop` command yet.
- GigaCode command invocation and `--resume` behavior have not been verified against the installed local CLI.
- Verification using OpenSpec plus Gradle/Maven is not wired into a workflow engine yet.
- No cross-process lock exists yet; do not run two processes against the same change concurrently.
- State replacement is atomic, but writing `state.json` and appending `events.jsonl` are not one atomic transaction. `state.json` is authoritative if a crash occurs between those writes.

`start` records existing uncommitted changes as part of the baseline and warns when the worktree was dirty. It does not attribute those changes to the agent and does not revert any files.

## Requirements and setup

Python 3.11+ is required. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

No third-party runtime dependencies are required.

## Commands

Diagnose tool availability and OpenSpec compatibility:

```bash
workflow doctor --repo /path/to/java-repo --change my-change
```

Initialize a workflow record:

```bash
workflow start my-change --repo /path/to/java-repo
```

Display status:

```bash
workflow status my-change --repo /path/to/java-repo
# Or, if there is exactly one run:
workflow status --repo /path/to/java-repo
```

Include the full event journal:

```bash
workflow status my-change --repo /path/to/java-repo --events
```

If not installed, these commands can also be run from the repository root with `PYTHONPATH=src python -m workflow_orchestrator.cli ...`.

## State storage layout

For a change called `add-loyalty-feature`:

```text
<target-repository>/.workflow/runs/add-loyalty-feature/state.json
<target-repository>/.workflow/runs/add-loyalty-feature/events.jsonl
```

The runtime state is ignored using the repository's local Git exclude file, keeping the developer's tracked files unchanged.

## Architecture direction

The orchestrator controls the process, OpenSpec owns the specification, GigaCode performs AI implementation, and Git/build checks provide observable evidence. The initial implementation is deliberately narrow and will be expanded in stages.

Reference: https://github.com/anyoneanderson/agent-skills
OpenSpec CLI reference: https://openspec.dev/docs/cli
