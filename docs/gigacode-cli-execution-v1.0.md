# GigaCode CLI execution integration — v1.0

This update connects the existing workflow state, approval service, and GigaCode adapter to the `workflow` CLI. It is a local integration milestone; run the automated tests before trying a real agent task.

## Commands

Start a workflow as before (this performs preflight and creates state only):

```bash
PYTHONPATH=src .venv311/bin/python -m workflow_orchestrator.cli start <change-id> --repo .
```

Execute a prompt against the initialized run:

```bash
PYTHONPATH=src .venv311/bin/python -m workflow_orchestrator.cli run <change-id> --repo . --prompt "Implement the requested OpenSpec change"
```

If GigaCode reports a permission denial, the command stores the session ID and changes the run to `WAITING_FOR_APPROVAL`.

Inspect the request:

```bash
PYTHONPATH=src .venv311/bin/python -m workflow_orchestrator.cli status <change-id> --repo .
```

Record a human decision:

```bash
PYTHONPATH=src .venv311/bin/python -m workflow_orchestrator.cli approval <change-id> --repo . --decision approve
```

Consume the decision and resume the saved session:

```bash
PYTHONPATH=src .venv311/bin/python -m workflow_orchestrator.cli resume <change-id> --repo .
```

To provide a continuation prompt, add `--prompt "Continue the task ..."`.

## Permission safety

The default GigaCode CLI mode remains `default`. An approval in the orchestrator records a human decision; it does **not** rewrite GigaCode's own permission rules. Therefore a resumed operation may be denied again, creating a new approval request.

The CLI supports an explicit override such as `--gigacode-approval-mode auto-edit`, but that mode can allow more file edits than the single operation that prompted the approval. Use it only when that broader permission is acceptable. The orchestrator never escalates the mode automatically.

A successful GigaCode turn moves the workflow to `VERIFYING`, not `COMPLETED`. Review the diff and run project verification before treating the task as complete. A turn with no final result, a CLI error, or a non-permission execution failure moves the workflow to `FAILED`; permission denials move it to `WAITING_FOR_APPROVAL` even when the final JSON says `is_error: false`.

## Scope and limitation

The adapter currently captures and parses NDJSON after the CLI process exits; this is not a live interactive approval bridge. The workflow pauses after a permission denial and resumes a saved session in a new CLI process after a recorded decision. It does not grant a narrowly scoped, one-operation permission inside GigaCode.
