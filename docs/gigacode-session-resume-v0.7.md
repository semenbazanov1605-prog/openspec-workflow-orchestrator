# GigaCode session resume (v0.7)

The adapter now supports `GigaCodeAdapter.resume_prompt(cwd, session_id, prompt, approval_mode="default")`.

- The supplied session ID is passed to `gigacode --resume`.
- The call uses `--output-format stream-json` and parses the final result using the same rules as a new session.
- `default` remains the default approval mode. The adapter never automatically changes a denied operation to `auto-edit`.
- `auto-edit` is accepted only when explicitly supplied by the caller. It may permit broader edits and should only be selected after the orchestrator's policy and human decision authorize that scope.
- Empty session IDs and unknown approval modes are rejected before invoking the CLI.

## Important integration boundary

This update adds the adapter capability, not a complete live approval loop. A caller must persist `GigaCodeResult.session_id`, detect `needs_approval`, persist the pending request and transition the workflow to `WAITING_FOR_APPROVAL`. After an explicit decision, the execution layer must choose an allowed approval mode and call `resume_prompt`. The adapter does not infer that approval of one denied write grants blanket `auto-edit` permission. The CLI process is still run to completion and NDJSON is parsed after exit; this is not live event streaming.

## Verified behavior

A manual experiment confirmed that `--resume <session_id>` reused the prior session and that a subsequent call with `--approval-mode auto-edit` created the file. This establishes session continuation, but does not establish a narrow one-operation approval mechanism. Do not treat `auto-edit` as equivalent to approval of only the single denied tool call.
