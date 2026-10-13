# GigaCode approval resume — v0.9

This milestone adds the service-layer operation `resume_after_approval(...)`.
It consumes a persisted `approve` decision, resumes the stored GigaCode session
through `GigaCodeAdapter.resume_prompt`, and routes the returned turn back through
`handle_gigacode_result`.

## Behavior

- Requires `WAITING_FOR_APPROVAL`, an explicit persisted `approve` decision, and a saved `gigacode_session_id`.
- Revalidates the persisted action against the workflow's approval policy.
- Accepts `approval_mode` explicitly; defaults to `default`. It never switches to `auto-edit` by itself.
- If the resumed turn is denied again, a new approval request is persisted.
- If the CLI adapter raises, the error is persisted and the workflow remains recoverable in its active state.
- A successful CLI turn is not considered verified code. Review the diff and run workflow verification separately.

## Important limitation

This is a service-layer API, not yet a complete interactive CLI command. The human decision must already be persisted using `record_approval_decision`. The caller invokes `resume_after_approval` with a deliberate prompt. GigaCode's own permission rules still apply: a human approval recorded in orchestrator state does not itself override a CLI deny rule. If the default mode denies the operation again, the workflow returns to `WAITING_FOR_APPROVAL`. Choosing `auto-edit` must be a separate, explicit operator decision because it grants broader edit capability.

## Example

```python
from pathlib import Path
from workflow_orchestrator.approval_service import resume_after_approval

report = resume_after_approval(
    Path("/path/to/repository"),
    "my-change",
    prompt="Continue the previously requested change, limited to the approved operation.",
    approval_mode="default",
)
print(report)
```

## Validation

The update adds tests for successful resumed turns, repeated permission denials,
missing approval/session data, and adapter errors. These use a fake adapter and do
not require GigaCode CLI to be installed. Real CLI integration still needs testing
on the work computer.
