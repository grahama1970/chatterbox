# WebGPT Architecture Review: Journal -> Memory -> Persistent Tau

## Objective

Define the smallest implementation patch and proof for one accepted physical
RealtimeSTT listener event to drive Memory speaker resolution and intent, then
one bounded persistent Tau subagent tick, preserving native event lineage.

## Proven Inputs

- Physical hot-mic receipt:
  `/tmp/embry-physical-hot-mic-qualification/run/receipt.json`
  - live=true, mocked=false
  - 10 unique wake/listen cycles
  - 1,495 contiguous journal events
  - restart/resume and capture reconnect passed
- Physical Horus enrollment:
  `/tmp/embry-horus-enrollment-physical/physical-enrollment-receipt.json`
  - 3 physical enrollment samples
  - 2 held-out Horus samples accepted
  - 2 impostors rejected
  - threshold 0.75, observed margin 0.280912
- Memory resolution:
  `/tmp/embry-horus-enrollment-physical/memory-resolution/receipt.json`
  - held-out Horus -> known/horus_lupercal
  - Embry self-audio -> unknown, personal memory blocked

## Existing Tau Proof Lane

Files:

```text
/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/proofs/tau/embry-chat-static-query-live/goal-packet.json
/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/proofs/tau/embry-chat-static-query-live/dag-contract.json
/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/proofs/tau/embry-chat-static-query-live/command-specs/embry-chatterbox/tau-dispatch-command.json
/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/proofs/tau/embry-chat-static-query-live/scripts/run_embry_chat_static_query_handoff.py
```

Current adapter problem:

1. Calls `run.sh embry-chat-static-query-live --play-local ...`.
2. Reads a global `latest.json` afterward.
3. Does not claim/consume an explicit journal event.
4. Does not propagate native listener `event_id`, `sequence`, `session_id`, or
   `turn_id` into Memory and Tau.
5. Can therefore pass using unrelated latest evidence.

## Current Contracts

Memory:

```text
POST /speaker/resolve
  -> known: speaker_id=horus_lupercal
  -> recall_profile=speaker_conversation_memory
  -> allow_personal_memory=true
POST /intent with speaker_resolution
```

Tau:

```text
tau.dag_contract.v1
tau.agent_handoff.v1
tau.persistent_subagent.v1
session_mode=persistent
tau_control=bounded_receipt_gated_ticks
unbounded_autonomy_allowed=false
```

Journal authority:

```text
agent-skills/skills/embry-voice-control SQLite journal
RealtimeSTT publishes canonical listener events
```

## Required Singular Proof

One explicit accepted physical listener event must produce:

```text
listener.final_transcript event
-> speaker/resolve known horus_lupercal
-> memory /intent
-> Tau persistent subagent bounded tick
-> tau.agent_handoff.v1
```

Every receipt must preserve:

```text
event_id
event sequence
session_id
turn_id
causation_id/correlation_id where supported
source journal hash or database identity
physical speaker profile hash
Memory speaker-resolution receipt/path/hash
Memory intent response/path/hash
Tau DAG goal hash
persistent_subagent receipt
```

## Fail-Closed Cases

- Event missing or not `listener.final_transcript`.
- Event/session/turn mismatch.
- Speaker resolution is unknown or ambiguous.
- `allow_personal_memory` is false.
- Memory intent does not contain the same speaker-resolution context.
- Tau handoff changes session/turn or omits source event.
- Adapter reads any global `latest.json` not explicitly named by the start
  handoff.
- Duplicate execution of the same source event.

## Constraints

- No Chatterbox call in this rung.
- No UI, orb, replay, or browser work.
- No source WAV or typed prompt substituted for the selected live event.
- Memory does not compute embeddings.
- Tau receives one bounded tick; no unbounded autonomy.
- Reuse the existing DAG and persistent-subagent validation where possible.
- Commit only relevant agent-skills/Tau files.

## Questions

1. Should the start handoff carry an explicit journal event payload plus receipt
   hash, or only a journal locator that the adapter claims transactionally?
2. Which component should own claim/ack/idempotency for this first proof?
3. What is the minimal patch to the current DAG, command spec, and adapter?
4. What exact receipt schemas and acceptance assertions make this causally
   stronger than the current latest-file proof?
5. Give exact file ownership and a deterministic run command for the first
   non-Chatterbox proof.

Return an implementation-oriented answer. Do not propose UI or broaden this
rung.
