# Workflow state layer (increment 2)

This increment adds the first implementation of the workflow's durable state model.
It does not yet run GigaCode or coordinate the full workflow.

## Files added

- `src/workflow_orchestrator/models.py`: versioned serializable state plus status and phase enums.
- `src/workflow_orchestrator/state_machine.py`: pure transition rules; invalid transitions raise `InvalidTransitionError`.
- `src/workflow_orchestrator/state_store.py`: atomic `state.json` writes and an append-only `events.jsonl` log.
- `tests/test_state_machine.py`: transition and phase-mapping tests.
- `tests/test_state_store.py`: persistence, invalid data, event log, and path validation tests.
- `.gitignore`: ignores Python-generated files, virtual environments, and local workflow state.

## Storage layout

For an example change ID `add-loyalty-feature`, state is stored at:

```text
<repository>/.workflow/runs/add-loyalty-feature/state.json
<repository>/.workflow/runs/add-loyalty-feature/events.jsonl
```

`.workflow/` is local runtime state and should not be committed by default.

## API sketch

```python
from pathlib import Path
from workflow_orchestrator.models import WorkflowState, WorkflowStatus
from workflow_orchestrator.state_machine import transition
from workflow_orchestrator.state_store import StateStore

store = StateStore(Path("/path/to/repository"))
state = WorkflowState.new(change_id="some-change", repository_path="/path/to/repository")
store.create(state)
state = transition(state, WorkflowStatus.RUNNING)
store.save(state, event_type="implementation_started")
```

## Current limits

- There is no CLI command wired to this state layer yet.
- There is not yet a cross-process per-change lock; that should be added before concurrent production use.
- State-file replacement is atomic, but the state file and event log are not one atomic transaction. On a crash between those writes, state is authoritative and the event log may omit the final event.
- `attempt_count` is persisted but not automatically changed by the state machine; the engine/retry policy will own those decisions.
