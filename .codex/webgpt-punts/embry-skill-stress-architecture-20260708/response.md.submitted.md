# WebGPT / create-architecture request: Embry skill-backed stress testing architecture

We need architecture help for the Embry voice/chat system. This is not a minor bug fix.

## Current goal

Stress test Embry voice/chat system to identify concrete failures across:

- RealtimeSTT ingress
- speaker identity / diarization
- memory/Tau routing
- direct skill access
- Chatterbox speech
- shared Chat UX sync
- orb sync
- replay
- interruption / barge-in

## User requirement update

The human clarified that Embry must be able to ask and answer an effectively unlimited number of questions from:

1. SPARTA corpora / SPARTA QRA / compliance evidence
2. persona_memory, especially Horus-scoped and Embry-scoped conversational memory
3. Brave Search / external research
4. direct skills via Tau, such as create-figure, analytics, create-evidence-case, SPARTA validators, memory, Brave Search, and voice-control skills

This likely requires 200+ tests at minimum and should be expandable beyond that. The tests must exercise voice and chat simultaneously when the lower rungs are ready. Embry must use memory-first routing, Tau as the tool/router authority, and answerability gates before Chatterbox speech.

## Current repo facts

Chatterbox fork has a FastAPI Chatterbox/Tau voice endpoint at `/tau/voice-render`.

Recent deterministic work:

- Commit `d3a0762 Block unanswerable Tau voice renders` pushed to `grahama1970/chatterbox@main`.
- Live receipt `/tmp/chatterbox-fork-agent-out/embry-answerability-runtime-block/20260708T010111Z-answerability-runtime-block/receipt.json` has `mocked=false`, `live=true`, `ok=true`, `case_count=12`, `failed_gates=[]`.
- That receipt proves `/tau/voice-render` rejects `block_before_speech` answerability decisions and produces no Chatterbox `finished_response_audio`.
- It does not fix upstream memory answer quality.

Known failures from current stress receipts:

- Memory `/answer` returns unrelated SPARTA/persona records for some questions.
- Twelve simple SPARTA/persona/memory-miss cases computed `block_before_speech`.
- Tone/emotion route fails several negative or overlap scenarios.
- Tau tool orchestration route currently fails because no `tau.agent_handoff.v1` work order or DAG receipt is created.
- Chat UX sync, replay, orb sync, browser mic ASR usability, interruption, and end-to-end RealtimeSTT -> memory/Tau -> Chatterbox -> Chat UX remain incomplete or only partially proven.

Current matrix:

- `docs/EMBRY_STRESS_SESSION_MATRIX.json` has 200 sessions.
- 10 route families x 5 difficulties x 4 questions = 200.
- Status counts: 9 passed, 31 failed, 160 not_run.
- Route families are currently: memory.sparta_qra, memory.persona_memory, memory.persona_memory.fail_closed, brave-search.source_receipt, tau.agent_handoff, ux-lab.shared_chat, chatterbox.turn_control, memory.speaker.resolve, realtimestt.factory_capture, memory.intent.voice_delivery.

## Architecture question

Design the next architecture and proof ladder for an expandable Embry stress harness that supports 200+ and eventually unlimited generated tests across SPARTA corpora, persona_memory, Brave Search, and direct skills through Tau.

Please produce:

1. A source-derived numbered architecture model with components and event flow.
2. Clear implemented vs intended/missing status labels.
3. A recommended schema for a generated stress session/test case.
4. A recommended schema for a skill call receipt and answerability receipt.
5. The execution ladder/rungs to get from current state to a full live loop.
6. Exact pass/fail gates for the first 5 implementation steps.
7. Which repo/component should own each part: chatterbox, agent-skills, memory, tau, ux-lab, RealtimeSTT.
8. How Embry should get direct skill access without letting UI or Chatterbox bypass Tau.
9. How to keep tests non-mocked and prevent static fixture theater.
10. A create-architecture-ready YAML diagram of components and connections.

Constraints:

- Chatterbox is the renderer/Tau voice ingress, not the reasoning layer.
- Tau is the tool/router authority.
- Memory is first for identity, recall, intent, answerability, and tone.
- Brave Search must be a real external research route with source receipts.
- The shared Chat UX must display the same event journal that voice uses.
- Chatterbox must not speak failed or unanswerable responses.
- Every skill call must have a receipt before Embry speaks from it.
- UI work should not be proof authority; event journal receipts should be.
- We need concrete pass/fail, not aspirational dashboard states.

Return a concise but complete architecture response and include YAML suitable for the local `create-architecture` skill.

## Latest human clarification

The human wants this architecture to drive creation of all additional tests, and the agent should continue asking clarifying questions until the 200+ test suite is complete and working as expected. Please include the minimum clarification interview tree needed before implementation, and recommend defaults where possible so the agent can proceed without drifting.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260708T010609Z:fa15614e>>>

Do not print anything after that marker.
