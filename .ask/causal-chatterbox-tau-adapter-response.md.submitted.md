# WebGPT Review: Tau adapter runtime blocker before causal Chatterbox render

## Objective

Choose the smallest correct repair that lets one physical listener event emit
`tau.turn_plan.v1`, then causally render that exact plan through Chatterbox.

## Proven live evidence

- Physical Jabra microphone transcript receipt accepted locally.
- Transcript: `Hey Embry, what is the capital of France?`
- Source event: `listener.final_transcript.e05728f278813654`, sequence `29`
- Session: `physical-hot-mic-20260711T010233Z-2668d0b9`
- Turn: `listener-process-1`
- Audio SHA-256: `9e4fa38494f4228d0e79af9baecd1c2483ea801ada56d6bde9ed0ef886da4cef`
- Physical Horus verification passed at `0.886888`.
- Speaker event: `speaker.verification.completed.26acf38666e41115`
- Memory `/intent` and `/answer` both executed live. The Memory answer was
  irrelevant to the capital-France query, so the existing
  `build_tau_response_plan()` helper should classify it as a memory miss and
  select the existing static answer `The capital of France is Paris.`

## Intended patch

The existing sibling lane was extended so the Tau node reads immutable Memory
intent/answer receipts, calls the mature
`embry_voice_control.embry_chat.build_tau_response_plan`, emits
`tau.turn_plan.v1`, and returns its locator/hash in `tau.agent_handoff.v1`.

## Two focused failures

Failure:
`ModuleNotFoundError: No module named 'embry_voice_control'`

After adding the skill `src` path, failure became:
`ModuleNotFoundError: No module named 'loguru'`

Tau warns that the active Embry skill virtualenv does not match Tau's `.venv`
and ignores it. The current command spec invokes plain `python3`:

`embry-journal-memory-tau-live command spec`

## Constraints

- Do not duplicate static answer or memory-miss policy in the proof adapter.
- Do not let Chatterbox reason or invent text.
- Keep one bounded Tau tick.
- Preserve exact source/session/turn/receipt hashes.
- No UI, orb, or replay in this rung.
- A third speculative attempt is forbidden.

## Question

Which repair is correct and smallest?

1. Change the Tau command spec to execute the adapter through
   `uv run --project <embry-voice-control-skill-root> python <adapter>`,
   ensuring the skill dependencies are available; or
2. Extract `build_tau_response_plan` into a dependency-free module imported by
   both the production Embry path and the Tau adapter; or
3. Another existing Tau command-wrapper mechanism that preserves the correct
   environment without copying policy.

Return the exact patch, deterministic tests, and live retry acceptance fields.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260711T010952Z:668b0282>>>

Do not print anything after that marker.
