# Project Knowledge: chatterbox

**Last updated:** 2026-07-02 08:48 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-07-01: Chatterbox fork is now the active replacement path for PersonaPlex-style voice-agent output. PersonaPlex remains out of the factual answer path. The fork has a FastAPI Chatterbox Turbo server on http://127.0.0.1:8018 using CUDA in Docker, OpenAI-compatible Whisper ASR on the Docker network, sentence-aware ~300-character chunking, accepted-audio cache, ASR-gated candidate selection, raw PCM chunk streaming, and interruption handling with stale old chunks skipped. Latest live bundle receipt: /tmp/chatterbox-fork-agent-out/full-live-sanity-20260701T235058Z/full-live-sanity.json. Scope: live transport/ASR/cache/stream/interruption smoke only; it does not prove full conversational agent quality, memory retrieval correctness, brave-search integration, or subjective voice preference.
- 2026-07-01 WebGPT compact review of the Chatterbox fork returned usable reviewer evidence via Surf transport proof_status=response_proven. Main review risks before commit-ready cleanup: public request-level ASR base URL and ASR API-key environment selection are a security boundary risk; global model.conds mutation needs a render/GPU lock or queue; accepted-audio cache needs stricter key/manifest revalidation and atomic writes; cache reset should avoid host/container ownership mismatch; stream receipts need decode/RMS/order/progressive proof; interruption receipts need a timeline proving zero old-turn bytes after cancel; explicit missing ref_audio should fail closed; reference roots should narrow to voice-only assets; wait activity allow_singing metadata needs correction; Turbo 300-character safety should be enforced or clearly documented as advisory. Review artifact: /tmp/chatterbox-webgpt-review-20260701T235058Z/webgpt-compact-response.md.
- 2026-07-01 follow-up hardening addressed the highest-risk WebGPT review items in the Chatterbox fork: removed public request-level ASR base URL/API-key env overrides from SynthesisBatchRequest, moved ASR routing to server-side CHATTERBOX_ASR_OPENAI_BASE_URL/CHATTERBOX_ASR_API_KEY_ENV, added a render_lock around model.prepare_conditionals/model.generate to prevent model.conds bleed, made explicit reference audio fail closed with existence/type/size checks, added accepted-audio cache schema/version/hash manifest fields with atomic writes and SHA mismatch rejection, enforced the 300-character Turbo hard cap while preserving requested_max_chars, fixed allow_singing metadata, added stream RMS/clipping/chunk timing proof, and added interruption_timeline proof for zero old-turn bytes after cancel. Latest hardened live bundle: /tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T001234Z/full-live-sanity.json. Checks: py_compile exit 0; targeted pytest 33 passed, 2 warnings; git diff --check exit 0; live bundle ok=true with cache fill 0/3 hits, cache hit 3/3 hits, stream first byte 1646.48 ms, stream RMS 1088.991, clipped_ratio 0.0, interruption stale_skipped_count 2 and post_cancel_old_turn_audio_bytes_emitted 0.
- 2026-07-01 final deterministic follow-up added a render-lock regression test with concurrent fake-model syntheses using different reference audio. This covers the WebGPT model.conds bleed risk at unit level without requiring local CUDA torchaudio. Latest deterministic checks after this addition: targeted pytest 34 passed, 2 warnings; git diff --check exit 0. No server code changed after the hardened live bundle /tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T001234Z/full-live-sanity.json.
- 2026-07-01 live proof gap closed for duck/stop controls. Added scripts/smoke_turn_controls.py and chained it into scripts/smoke_full_live_sanity.py. Latest full live bundle /tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T001642Z/full-live-sanity.json has five child receipts: ASR cache fill ok with 0 cache hits, ASR cache hit ok with 3 cache hits, stream endpoint ok with first_byte_ms 1476.763 and 620160 bytes, interruption ok with stale_skipped_count 2, and turn_controls ok with action_order [cancel, duck, stop] and final_control cancelled=true, stale_chunks_should_skip=true, ducked=true, stopped=true. Deterministic checks after this change: py_compile exit 0; targeted pytest 34 passed, 2 warnings; git diff --check exit 0.
- 2026-07-01 completion-audit follow-up: added a direct crossfade unit test for append_with_crossfade and performed audio playback sanity for /tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T001642Z/stream-endpoint/stream.wav with pw-play exit 0. Deterministic checks after this final addition: py_compile exit 0; targeted pytest 35 passed, 2 warnings; git diff --check exit 0. Current objective requirements have direct file/test/live evidence: 300-character sentence-aware Turbo chunking, latency events, voice conditioning cache and render lock, hum/sing/beatbox/primes/check-in wait registry, chunk-stream endpoint with crossfade, cancel/duck/stop APIs and stale-chunk receipts, ASR verification harness, and reference audio sandboxing.
- 2026-07-02: main now includes the conversation sanity ladder rungs 1-6, stream turn-cancellation integration, and memory-gated blessed-QRA audio cache. Stream requests accept turn_id and stop when turn_controls mark cancelled/stopped; live receipt /tmp/chatterbox-fork-agent-out/stream-cancel-20260702T1150/stream-cancel.json shows mocked=false, live=true, baseline_bytes=65536, old_turn_bytes_after_cancel=0, failed_gates=[]. Blessed QRA playback requires a near-exact memory gate by default: blessed_qra_memory_key must match the approved QRA entry, blessed_qra_memory_similarity must meet the configured threshold, and review_status must be approved/blessed/verified. scripts/bless_qra_audio_variants.py can generate five Embry audio variants per blessed QRA. Live receipt /tmp/chatterbox-fork-agent-out/blessed-qra-cache-hit-20260702T1214.json shows mocked=false, live=true, cache_hit=true, entry_id=qra-smoke-si, variant_id=gentle, memory_gate_passed=true, client_elapsed_ms=157.103, failed_gates=[]. Deterministic checks: py_compile exit 0; targeted pytest 39 passed, 2 warnings; git diff --check exit 0.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-01 | Initialize project knowledge | Enable shared human/agent context |
| 2026-07-01 | Use Chatterbox fork full-live-sanity receipt as the consolidation gate | The combined runner chains ASR cache fill, ASR cache hit, stream endpoint, and interruption smoke into one receipt with mocked=false/live=true and explicit does_not_prove boundaries. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?
- [ ] Should the next Chatterbox fork patch prioritize P0 security/concurrency fixes before Embry subagent conversation testing?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
