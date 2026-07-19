# Battle Backend Phase 1 Architecture Review

## Request

Use `create-architecture` reasoning to collaborate on **backend-only Battle Phase 1** before implementation.

The project agent should not start coding until Phase 1 boundaries, acceptance evidence, and open clarifying questions are aligned.

Please assess the proposed backend Phase 1, return a source-derived step model, label implemented vs intended/missing behavior, and ask clarifying questions for the next round. Keep the result backend-only. Do not design frontend UX in this round.

## Current Repository State

Repo: `/home/graham/workspace/experiments/agent-skills`

Relevant skill contract from `skills/battle/SKILL.md`:

- Battle is the control plane.
- Tau owns subagent execution and model calls.
- Battle owns team selection, Docker runtimes, scorekeeping, artifacts, and memory promotion.
- Generated code is not proof.
- Compiled code is not proof.
- Runnable code is not exploit success.
- Target contact is not exploit success.
- Judge replay is required before exploit-success claims.

## Implemented / Proven Rungs

### PR1 Exploit Combiner Proof

Implemented fixture-backed specimen lifecycle.

Known non-claims:

- no live Tau generation
- no child materialization
- no Judge exploit success

### PR2 Spawn Architect Proof

Implemented fixture-backed DAG birth contract.

It proves:

- Battle can construct a child knowledge packet from parent specimen evidence.
- Battle can author a `tau.dag_contract.v1` child exploit-synthesis DAG.
- Battle can validate private-artifact exclusions and claim boundaries.
- Tau execution is deferred.

Known non-claims:

- no live Tau DAG execution
- no child exploit code
- no child target run

### PR3a Command-Spec Canary Repair

Implemented Battle-owned Tau command specs and `battle_skill.child_dag_node_adapter`.

It moved the blocker from missing command specs to real node capability.

### PR3b Research Combiner Boundary

Implemented and pushed.

Known evidence from prior local runs:

- commit `74f82a2e1 battle: add PR3b Tau research combiner boundary`
- commit `9c9fa061c84aa30a126aa425ffb6fba6e3fc20fe battle: add normalized PR3b proof card fixture`
- live canary produced:
  - `lineage-summarizer PASS`
  - `research-scout PASS`
  - `method-combiner PASS`
  - `exploit-code-author BLOCKED`
  - `fixture_fallback_used: false`
  - `judge_verified_exploits: 0`

Qualification:

The PR3b research node executes for real through Tau command dispatch, but its source packet is deterministically assembled from known Snyk, Python, and GitHub references. It records `method: manual`, `external_tool_called: false`, and `provider_live: false`. It is source-bearing design input, not live web research proof.

## Current Blocker

The live Tau child DAG now blocks at:

```text
exploit-code-author BLOCKED
PROVIDER_OR_TAU_CODE_AUTHOR_ADAPTER_MISSING
```

No backend code should label Battle-written template code as Tau-authored provider output.

## Proposed Phase 1 Target

Recommended Phase 1 should be **PR3c real provider-authored exploit-code author boundary**, not the whole genetic engine.

Phase 1 proposed backend objective:

```text
Battle PR3b output
→ Tau executes exploit-code-author node
→ real provider/model is invoked through Tau/provider path
→ exploit_specimen.py is materialized as an artifact
→ specimen.json records provider authorship
→ provider-authorship receipt records model/provider/run/hash provenance
→ Battle validates no private artifact references
→ Battle validates no exploit-success claims
→ Tau advances to compile-repair
→ compile-repair may PASS or BLOCK, but Phase 1 still succeeds if the provider-authored code boundary is proven
```

Expected Phase 1 canary result:

```text
lineage-summarizer       PASS
research-scout           PASS
method-combiner          PASS
exploit-code-author      PASS
compile-repair           BLOCKED or PASS
Judge verified exploits  0
fixture_fallback_used    false
```

## Proposed Files

Add:

```text
skills/battle/src/battle_skill/child_dag_code_author.py
skills/battle/src/battle_skill/provider_artifact_validator.py
skills/battle/contracts/exploit-code-author.prompt.v1.json
skills/battle/schemas/battle.child_code_author_receipt.v1.schema.json
skills/battle/schemas/battle.provider_authorship_receipt.v1.schema.json
skills/battle/schemas/battle.exploit_specimen.v2.schema.json
skills/battle/tests/test_child_dag_code_author_contract.py
skills/battle/tests/test_provider_artifact_validator.py
skills/battle/tests/test_pr3c_live_code_author_boundary.py
```

Modify:

```text
skills/battle/src/battle_skill/child_dag_node_adapter.py
skills/battle/src/battle_skill/live_tau_child_dag_canary.py
skills/battle/src/battle_skill/tau_child_dag.py
skills/battle/README.md
skills/battle/HANDOFF_BACKEND.md
```

## Proposed Provider Boundary

Battle should not call an LLM provider directly.

Preferred path:

```text
Battle code-author node
→ writes exploit-code-author-work-order.json
→ invokes Tau provider/coding adapter
→ Tau invokes configured provider/model
→ provider materializes code into Tau artifact directory
→ Battle validates artifacts
→ Tau continues the DAG
```

If Tau cannot materialize arbitrary files, the preferred fix is to add a generic Tau artifact-authoring provider adapter, not a Battle-specific hidden model call.

## Work Order Shape

```json
{
  "schema": "battle.exploit_code_author_work_order.v1",
  "battle_id": "battle-004",
  "child_lane_id": "payload-857-child-dag-001",
  "goal_hash": "sha256:...",
  "inputs": {
    "lineage_summary": "lineage_summary.json",
    "research_receipts": "research_receipts.json",
    "candidate_methods": "candidate_methods.json",
    "exploit_genome": "exploit_genome.json",
    "public_target": "arena/team-public/target"
  },
  "required_outputs": [
    "exploit_specimen.py",
    "specimen.json",
    "provider-authorship-receipt.json"
  ],
  "constraints": [
    "Do not claim exploit success.",
    "Do not reference private Arena artifacts.",
    "Generated code may be incorrect.",
    "Materialize code as an artifact; do not return code only in prose.",
    "Do not execute the exploit from the provider node."
  ]
}
```

## Required Outputs

```text
exploit_specimen.py
specimen.json
provider-authorship-receipt.json
exploit-code-author-node-receipt.json
provider stdout/stderr/session artifacts
```

Provider receipt must record:

```text
provider
model
provider_run_id
prompt/work-order hash
input artifact hashes
output code hash
provider_live: true
agentic: true
fixture_fallback_used: false
```

## Phase 1 Must Not Claim

```text
compiled child code
runnable child code
target contact
exploit success
Blue detection
Blue kill/block
memory promotion
genetic population completeness
```

## Questions For WebGPT Round 1

1. Is the proposed Phase 1 boundary correctly scoped, or should Phase 1 include compile-repair as mandatory?
2. Should Battle implement `child_dag_code_author.py` as a thin wrapper around an existing Tau provider adapter, or should the generic Tau artifact-authoring adapter be built first?
3. What exact provider-authorship receipt fields are needed to prevent fixture/template code from being mislabeled as provider-authored?
4. What fail-closed tests are mandatory before any implementation can claim Phase 1 evidence?
5. What should the create-architecture diagram include for Phase 1 only, and what should be explicitly outside the diagram?

## Desired Output

Return:

1. A numbered source-derived Phase 1 backend step model.
2. Implemented vs intended/missing labels.
3. A recommended Phase 1 acceptance gate.
4. Required schemas/modules/tests.
5. Clarifying questions for the next round.
6. A `create-architecture` YAML diagram for Phase 1 only.

Do not return frontend implementation steps in this round.
