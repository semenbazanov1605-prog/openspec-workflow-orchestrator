# v1.0 update

This patch adds `workflow run` and `workflow resume` commands and connects them to persisted workflow state, the GigaCode stream adapter, and approval decisions.

Files in this patch:
- `src/workflow_orchestrator/cli.py` — adds `run` and `resume` commands.
- `src/workflow_orchestrator/execution_service.py` — orchestrates execution, approval consumption, session resume, and result-state transitions.
- `tests/test_execution_service.py` — tests success, denial, rejection, missing decision, repeated denial, and execution failure.
- `docs/gigacode-cli-execution-v1.0.md` — usage and permission caveats.

The patch is intended to be overlaid onto the v0.9 project. It is not a full source archive.
