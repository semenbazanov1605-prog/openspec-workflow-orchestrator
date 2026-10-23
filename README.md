# OpenSpec Workflow Orchestrator — local CLI prototype

A dependency-free Python CLI for incrementally building a safe workflow around an existing OpenSpec change and GigaCode CLI.

## Current features (v0.5.0)

- `workflow doctor --repo PATH --change CHANGE_ID`: read-only preflight checks for Git, OpenSpec status/validation, and GigaCode CLI availability.
- `workflow start CHANGE_ID --repo PATH`: runs preflight first; creates a persisted run only if all checks pass, then captures Git HEAD and worktree status as the baseline.
- `workflow status [CHANGE_ID] --repo PATH`: show saved state; if exactly one run exists, the change ID may be omitted.
- `workflow status CHANGE_ID --repo PATH --events`: include the complete event log.
- Versioned state model, validated state transitions, atomic `state.json` persistence, and append-only `events.jsonl`.
- Stores the preflight evidence in the initial workflow state.
- Persists the selected approval policy per run: `default`, `auto-edit`, or `plan`.
- Adds an action policy for read-only actions, file edits, commands, and unknown actions.
- Adds `WAITING_FOR_APPROVAL`, persistent approval request metadata, and an `approval` command to record a human decision.
- `.workflow/` runtime state is excluded through Git's local `.git/info/exclude`, not by editing the project's tracked `.gitignore`.
- Unit tests for adapters, state transitions, persistence, start/status services, and preflight gating.

## Important limitations

This version is **not yet the complete orchestrator**:

- `workflow start` does not invoke GigaCode to modify files. It only runs read-only preflight and creates the initial state.
- The preflight checks that the GigaCode executable exists on `PATH`; it does not launch an agent or prove that the implementation command's JSON contract works in the current environment.
- `workflow resume` and `workflow stop` are not implemented yet.
- Approval policy is currently an orchestrator-side model. It is not yet mapped to a running GigaCode session, and `workflow approval` records a decision but does not relay it to a live GigaCode prompt. The TTY / structured approval interaction must be tested on the target machine.
- GigaCode invocation and `--resume` behavior still need a live compatibility probe.
- Verification using OpenSpec plus Gradle/Maven is not wired into a workflow engine yet.
- No cross-process lock exists yet; do not run two processes against the same change concurrently.
- State replacement is atomic, but writing `state.json` and appending `events.jsonl` are not one atomic transaction. `state.json` is authoritative if a crash occurs between those writes.

`start` records existing uncommitted changes as part of the baseline and warns when the worktree was dirty. It does not attribute those changes to the agent and does not revert any files. If preflight fails, no workflow run is created and the command exits with code 1.

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

Run preflight checks without creating state:

```bash
workflow doctor --repo /path/to/java-repo --change my-change
```

If the executable name differs from `gigacode`:

```bash
workflow doctor --repo /path/to/java-repo --change my-change --gigacode-executable gigacode
```

Start a run only after preflight passes (manual approval policy is the default):

```bash
workflow start my-change --repo /path/to/java-repo
```

Persist a different policy for a new run:

```bash
workflow start my-change --repo /path/to/java-repo --approval-mode default
workflow start my-change --repo /path/to/java-repo --approval-mode auto-edit
workflow start my-change --repo /path/to/java-repo --approval-mode plan
```

Policy meaning in this orchestrator: `default` asks before edits/commands; `auto-edit` permits file edits but still gates commands; `plan` permits read-only analysis and denies mutating actions. This policy is persisted only; the live GigaCode session mapping has not yet been implemented.

Record a decision for an existing pending request:

```bash
workflow approval my-change --repo /path/to/java-repo --decision approve
workflow approval my-change --repo /path/to/java-repo --decision reject --note "Needs a revised plan"
```

A recorded decision remains pending until a future execution engine delivers it to the blocked CLI session. The current CLI does not yet send keystrokes or protocol events to GigaCode.

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

If the package has not been installed, commands can also be run from the repository root with `PYTHONPATH=src python -m workflow_orchestrator.cli ...`.

## State storage layout

For a change called `add-loyalty-feature`:

```text
<target-repository>/.workflow/runs/add-loyalty-feature/state.json
<target-repository>/.workflow/runs/add-loyalty-feature/events.jsonl
```

The runtime state is ignored using the repository's local Git exclude file, keeping the developer's tracked files unchanged.

## Approval design

See [`docs/approval-policy.md`](docs/approval-policy.md) for the policy table, persisted lifecycle, and current integration boundary.

## Architecture direction

The orchestrator controls the process, OpenSpec owns the specification, GigaCode performs AI implementation, and Git/build checks provide observable evidence. The initial implementation is deliberately narrow and will be expanded in stages.

Reference: https://github.com/anyoneanderson/agent-skills
OpenSpec CLI reference: https://openspec.dev/docs/cli
