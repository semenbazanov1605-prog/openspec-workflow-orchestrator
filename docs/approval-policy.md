# Approval policy (increment 5)

This increment makes approval behavior explicit in the workflow model. It adds a persisted approval mode, a `WAITING_FOR_APPROVAL` state, a pure action policy, and durable recording of a human decision.

## Modes

| Mode | Read-only action | File edit | Command / unknown action |
|---|---|---|---|
| `default` | Allow | Require human approval | Require human approval |
| `auto-edit` | Allow | Allow | Require human approval |
| `plan` | Allow | Deny | Deny |

This is the orchestrator's conservative policy. In particular, `auto-edit` does not imply blanket permission to execute arbitrary commands. The mode is persisted when a run is created.

## Approval lifecycle

1. An executor adapter supplies a structured action category and description.
2. `evaluate_action()` returns `allow`, `require-approval`, or `deny`.
3. For `require-approval`, `request_approval()` records the request and changes the run to `WAITING_FOR_APPROVAL`.
4. `workflow approval <change-id> --decision approve|reject` writes the human's decision into the pending request.
5. The run remains `WAITING_FOR_APPROVAL` until the execution engine has delivered that decision to the blocked executor. After delivery, the engine calls `finalize_approval_decision()`: approval resumes the prior `RUNNING` or `VERIFYING` status; rejection moves the run to `PAUSED`.

Keeping the run waiting after writing a decision is intentional. A persisted decision is not proof that a live CLI process actually received it.

## Current integration boundary

The current milestone does **not** inspect arbitrary GigaCode text looking for approval prompts and does **not** relay a decision to a live GigaCode terminal session. The actual CLI's structured approval event / TTY behavior must first be verified on the target machine. The new policy and persistence layer is ready for that adapter work, but the end-to-end interactive bridge remains outstanding.

No state schema version bump is required for this additive change: older state files lacking `approval_mode` and `pending_approval` load with the safe defaults `default` and `null`.
