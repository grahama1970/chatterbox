# Conversation Sanity Ladder Audit

Audit date: 2026-07-02

This audit maps the active goal to current evidence. It does not claim
production readiness, subjective voice quality, live microphone readiness, or
global memory salience correctness.

## Deterministic Checks

Latest deterministic checks after rung 6:

```bash
python -m py_compile scripts/smoke_conversation_ladder.py
PYTHONPATH=src pytest tests/test_conversation_ladder_smoke.py tests/test_asr_acceptance.py
python -m json.tool tests/fixtures/conversation_ladder/manifest.json >/dev/null
git diff --check
```

Observed result:

- `py_compile`: exit 0.
- `pytest`: 11 passed.
- `manifest.json`: valid JSON.
- `git diff --check`: exit 0.

## Live Receipts

All live receipts below are local artifacts under
`/tmp/chatterbox-fork-agent-out/conversation-ladder/`. Each passed receipt has
`mocked=false`, `live=true`, `ok=true`, and empty `failed_gates`.

| Rung | Receipt | Primary evidence |
|---|---|---|
| 1 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung1-live-20260702T111209Z/rung1.json` | File-backed listener input to ASR/TTS loop; input WER `0.0`; output WER `0.0`. |
| 2 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung2-live-20260702T111722Z/rung2.json` | Two-turn state; final `favorite_color=blue`; omitted-turn-1 fail-closed gate; all input/output WER values `0.0`. |
| 3 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung3-live-20260702T112209Z/rung3.json` | Memory-grounded Embry turn; memory key `embry_age15_19_b03_memory_040`; confidence `124.598`; output WER `0.0`. |
| 4 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung4-live-20260702T112513Z/rung4.json` | Interruption audio to ASR; `stale_skipped_count=2`; `post_cancel_old_turn_audio_bytes_emitted=0`; turn-control order `[cancel, duck, stop]`. |
| 5 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung5-live-20260702T112808Z/rung5.json` | Live Brave Search; latency `1732.789 ms`; three result URLs; wait text `I see.`; output WER `0.1429`. |
| 6 | `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung6-live-20260702T113313Z/rung6.json` | Three-turn emotional steering; cues `sensory_rain`, `relationship_kai`, `requested_gentleness`; memory key `embry_age15_19_b03_memory_040`; final state `gentle_followup`; all input/output WER values `0.0`. |

## Requirement Mapping

| Requirement | Evidence | Status |
|---|---|---|
| Comprehensive rung 1-6 ladder plan | `docs/conversation_sanity_ladder_v0.md` defines purpose, inputs, live paths, pass gates, schemas, claims, non-claims, and stop rules. | Satisfied |
| Listener input | Rungs 1-6 use file-backed WAV fixtures with ASR gates and receipt artifact metadata. | Satisfied for file-backed listener; live microphone remains out of scope. |
| ASR/TTS loop proof | Rungs 1-6 include live ASR input and Chatterbox TTS output ASR checks. | Satisfied |
| Memory-grounded turns | Rungs 3 and 6 query live memory, preserve returned keys/scores/text fields, and gate on scoped Embry evidence. | Satisfied |
| Interruption handling | Rung 4 records ASR interrupt input, stale old-turn skip proof, zero old-turn bytes after cancel, and live cancel/duck/stop controls. | Satisfied |
| Brave Search/tool latency | Rung 5 records a live Brave Search call, result URLs, measured latency, wait decision, and TTS/ASR output. | Satisfied |
| Dynamic emotional steering | Rung 6 records cue spans, memory evidence, emotion transition, utterance policy, and ASR-verified responses. | Satisfied |
| Receipt-backed validation | All six rungs have local JSON receipts with `mocked=false`, `live=true`, `ok=true`, and empty `failed_gates`. | Satisfied |

## Boundaries

The ladder still does not prove:

- live microphone capture or WebRTC transport,
- subjective voice preference,
- noisy-room robustness,
- globally correct memory salience ranking,
- production deployment readiness,
- long-running multi-tool orchestration.

Those are future rungs or separate acceptance contracts, not closure criteria for
this ladder artifact.
