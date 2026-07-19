# Embry Audio E2E Runner: Live Executor Repair

## Objective

Repair the current `embry_voice_control.audio_e2e` implementation so one selected two-turn case actually traverses the canonical live event spine. Do not redesign the architecture or add another harness.

## Human Decision

The 200-case campaign uses a mixed source strategy: physical Jabra qualification first, then a qualified Horus corpus/clone for scale. Source classes must remain explicit.

## Current Deterministic Evidence

- Chatterbox commit `502e9c4`: preserves Tau delivery arcs.
- RealtimeSTT commit `afc70dd`: managed physical listener.
- Agent-skills commit `e21d0c39b`: added `audio_e2e` run/resume/status/failure-bundle state and scripts.
- Agent-skills commit `72c428c3f`: fixed wrapper source-path handling and added the execution plan.
- Focused tests: `5 passed`.
- Hidden source-policy baseline: PASS.
- Browser-oracle: project `embry`, tab `837357645`, Desktop 2, exact conversation URL already bound.

## Actual Failure

The current runner is not a live executor.

1. `run_audio_e2e_rung.sh` is only a package CLI wrapper.
2. The plan calls unsupported flags: `--count 1 --source-mode ... --require-gates all` without a subcommand.
3. `runner.py` only creates stage state and does not invoke RealtimeSTT, speaker verification, Memory, Tau, Chatterbox, Jabra playback, Chat projection, orb, or replay.
4. Task 1 originally false-greened because its DoD checked only pre-existing compiler tests.
5. Task 2 then failed before audio with an import-path bug; that narrow bug is now fixed.

## Existing Components That Must Be Composed

- Managed RealtimeSTT listener in `grahama1970/RealtimeSTT`.
- `event_journal.py` and listener journal service.
- Journal -> Memory -> persistent Tau proof lane.
- Causal Chatterbox render script.
- `pipewire_playback.py` Jabra authority.
- `chat_projection.py`.
- Existing UX/orb/replay proof scripts and journal events.

## Constraints

- No typed transcripts, fixture responses, browser microphone, or global `latest.json`.
- No generic source WAV counted as physical live.
- One persistent Tau session with one bounded tick per turn.
- Every stage uses the same campaign/case/session/turn lineage.
- A failure freezes a bundle and resumes at the failed stage.
- First stop condition is exactly one complete two-turn physical SPARTA case.
- Do not produce a broad future plan. Return the smallest patch sequence and exact commands.

## Questions

1. Which existing concrete command or Python callable should `case_executor.py` invoke for each stage today?
2. What is the smallest exact file patch that makes `audio_e2e run` execute one real physical turn rather than initialize state?
3. How should the physical human prompt/arm/wait handshake work for two turns without passing expected text to RealtimeSTT?
4. Which currently proven UI/orb/replay commands can be called as-is, and which exact missing adapter is unavoidable?
5. Provide a source-derived implementation order with exact files, commands, receipt fields, and one-case PASS/FAIL stop condition.
6. Explicitly identify any current component whose claimed proof cannot be composed into one same-session case.

Return an implementation-ready answer. End with the Surf-provided sentinel.
