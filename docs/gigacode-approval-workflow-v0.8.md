# GigaCode approval workflow integration — v0.8

## What changed

`handle_gigacode_result(repository, change_id, result)` now connects the normalized GigaCode adapter result to persisted workflow state:

- stores the returned `session_id` in the workflow state;
- persists a `gigacode_turn_received` event and a normalized summary of the result;
- treats `permission_denials` as a denied operation even if the CLI result reports `is_error=false` or `subtype=success`;
- maps known file-writing tools to `file-edit`, shell/command tools to `command`, and unknown tools to `unknown`;
- creates an approval request using the existing policy service, moving a RUNNING/VERIFYING workflow to `WAITING_FOR_APPROVAL` when policy requires it;
- returns the original denial payload for diagnostics.

## Usage

Call the handler after `GigaCodeAdapter.run_prompt()` or `resume_prompt()` returns:

```python
result = adapter.run_prompt(repo, prompt)
report = handle_gigacode_result(repo, change_id, result)
```

The workflow must already exist and be in `RUNNING` or `VERIFYING` state.

## Important safety boundary

This version **does not automatically resume** the session after the human decision. The existing `workflow approval` command records a decision; it does not itself relay a decision to GigaCode. The observed CLI test succeeded only after explicitly selecting `--approval-mode auto-edit`, which permits a broader set of file edits than a single one-shot approval. The orchestrator must not silently elevate permissions or treat the approval record as proof that execution resumed.

The next milestone should add a deliberate resume command/policy that requires an explicit execution mode, resumes the saved `session_id`, passes the returned result back through this handler, and finalizes the approval only after the resumed result is inspected. The resume path must handle repeated denials and failed CLI invocations without losing the pending request.
