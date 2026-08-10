# Chatterbox Issue #25 Pace Effect Proof

Issue: https://github.com/grahama1970/chatterbox/issues/25

## Change

`/synthesize-batch` now publishes a top-level `pace_effect` receipt aggregated
from the per-render chunk receipts. Consumers can verify `applied`,
`tempo_factor`, and pre/post `duration_seconds` without mining `chunks[]`.

## Proof

- mocked: no for live curl proof; yes for the focused unit regression's model
  call stub, which proves endpoint wiring only
- live: yes for `/tmp/pace-proof.json` and
  `docs/proofs/tickets/issue-25-pace-effect-20260810/closure-evidence.json`
- command: `PYTHONPATH=src python3 -m pytest -q tests/test_agent_server_primitives.py`
- result: 50 passed, 3 warnings
- live command: POST `/synthesize-batch` twice against
  `http://127.0.0.1:8018`, with `pace=slow` and `pace=fast`
- live result: `closure-evidence.json` has `ok=true`, `failed_gates=[]`,
  slow `pace_effect.applied=true`, slow `tempo_factor=0.85`, fast
  `pace_effect.applied=true`, fast `tempo_factor=1.18`, and
  `fast_shorter_than_slow=true`

## Artifacts

- `closure-evidence.json`
- `slow-response.json`
- `fast-response.json`
