# GigaCode stream-json adapter (v0.6 integration step)

This update adapts the existing GigaCode wrapper to the stream-json output observed with GigaCode CLI 26.8.41.

## Observed protocol assumptions

- One JSON object is emitted per line.
- `system` / `subtype: init` includes `session_id`.
- `assistant` messages can contain `message.content` text blocks.
- The final `result` event includes `session_id`, `is_error`, and `permission_denials`.
- A `result` with `subtype: success` and `is_error: false` is **not enough** to declare success if `permission_denials` is non-empty.

## Current behavior

- Parses all NDJSON events after the subprocess exits.
- Retains the session ID, assistant text, result payload, and permission denials.
- Marks a turn unsuccessful when there is a permission denial, a non-zero exit code, an error result, a missing final result event, or a timeout.
- Defaults to `--approval-mode default`; this intentionally avoids silently enabling `auto-edit`.

## Limitations

This is not yet a live interactive approval bridge. It detects denials after the one-shot CLI call completes and exposes them as `needs_approval`; it does not answer a permission request while the process is running, retry the denied tool call, or automatically resume a session. Do not treat `workflow approval` as connected to a live GigaCode process yet.

The adapter is based on observed output from CLI 26.8.41 and should be integration-tested again if the CLI version or output schema changes.
