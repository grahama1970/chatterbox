# chatterbox#11 Strict Tau Voice v2 Consumer Proof

Date: 2026-08-02

## Scope

This proof covers `grahama1970/chatterbox#11`: Chatterbox accepts
`tau.voice_render_request.v2` on the existing `/tau/voice-render` route, fails
closed for unsupported versions or misspelled required v2 fields, preserves the
Tau lineage digest, and fences controls by complete v2 response identity.

## Implementation Summary

- Added strict Pydantic v2 models for Tau response identity, source lineage,
  delivery decision, segments, and control target.
- Kept v1 compatibility on `/tau/voice-render`.
- Changed route admission to raw JSON plus explicit schema dispatch, preventing
  FastAPI from silently parsing v2 payloads through the permissive v1 model.
- Added `supported_tau_voice_render_request_schemas` to `/health`.
- Added Chatterbox-side response identity registry and v2 control target
  evaluation for cancel/duck/stop.
- Added a standard-library PCM WAV combine fallback for compatible no-crossfade
  blessed-QRA audio, so cached/live readback does not require torchaudio.

## Deterministic Proof

```text
python -m ruff check src/chatterbox/agent/server.py tests/test_agent_server_primitives.py scripts/smoke_tau_voice_render_v2.py
```

Result:

```text
All checks passed!
```

```text
PYTHONPATH=src uv run --no-sync python -m pytest -q tests/test_agent_server_primitives.py tests/test_render_plan_parity.py tests/test_stream_manifest_lifecycle.py
```

Result:

```text
60 passed, 4 warnings in 2.88s
```

## Live Route Smoke

```text
PYTHONPATH=src uv run --no-sync python scripts/smoke_tau_voice_render_v2.py --allow-live
```

Result:

```json
{"ok": true, "receipt": "/home/graham/workspace/experiments/chatterbox/docs/proofs/tickets/issue-11-v2-consumer-20260802/live-smoke/receipt.json", "failed_gates": []}
```

Receipt invariants:

- `mocked: false`
- `live: true`
- `http_status: 200`
- `request_lineage_digest` equals Tau fixture digest
  `10242ccd97287926fbb0692163429ee95427e692dc63daf88f3a63b161b0e95b`
- `consumer_digest_matches: true`
- `finished_response_audio` exists and is non-empty
- stale wrong `response_id` cancel rejected with `stale_response_id`
- current cancel accepted with `current_response`
- duplicate cancel accepted idempotently with `already_cancelled`

Live receipt:

```text
docs/proofs/tickets/issue-11-v2-consumer-20260802/live-smoke/receipt.json
```

## Environment Note

Plain `uv run ...` currently attempts a full project solve and fails before
executing code because the optional `diarization` extra declares
`pyannote.audio>=4.0.0`, which requires `torchaudio>=2.8.0`, while the base
project pins `torchaudio==2.6.0` for Python `<3.14`. The proof therefore uses
`uv run --no-sync` against the existing project environment. This is an
environment/dependency issue separate from the v2 consumer behavior.
