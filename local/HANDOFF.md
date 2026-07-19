# Handoff Report: Chatterbox / Embry Live Voice

## -1. HANDOFF UPDATE 2026-07-19T17:35Z — bulk campaign running; how to operate without an agent

**State (all journal-verified at write time):** 92 of 300 cases counted
(`audio_e2e.case_completed` distinct sessions) = 1 physical + 12 pilot (campaign
`7af1cfc0…`) + 79 bulk (campaign `bf26de75…`, running). Latest heartbeat: 69
completed / 182 running / 7 blocked in the bulk campaign; runner alive. Chat
projections resolve 270/271 turns across every completed case (the 1 failure is
a correctly fail-closed overwritten artifact in the double-run
pilot persona_memory_miss session).

**Architecture (external oracle-reviewed, 2026-07-18):** two tiers.
Tier A physical air (Jabra speaker -> room -> C920 mic) anchors acoustics: 1
human case + 4 synthetic-air listener passes. Tier B bulk runs SILENTLY over
PipeWire loopback: clone WAV -> `pw-play --target embry_horus_input` (null
sink) -> sink monitor (`pw-record -P stream.capture.sink=true`) -> RealtimeSTT
(CUDA small.en) -> full spine. Sink `embry_chatterbox_output` reserved for
output-proof recapture. The null sink SUSPENDS when idle — a silent 48 kHz
keep-alive stream into `embry_horus_input` is REQUIRED during runs.

**Where everything lives:**
- Code: `agent-skills` branch `voice-campaign-20260718` (tip `a715869d4`;
  the checkout branch is contested by a "Pipeline Smoke" battle automation that
  force-moves `main` — merge to main only from this pointer).
  RealtimeSTT repo master has the listener commits (`f2b355c`..`7f321b1`).
- Campaign artifacts: session scratchpad
  `/tmp/claude-1000/-home-graham-workspace-experiments-chatterbox/8928d5f2-*/scratchpad/`
  (`full300_manifest.json`, `full300_state.json`, `full300_progress.log`,
  `campaign_full300/` captures). Assets:
  `chatterbox/logs/horus-clone-assets-full300-20260718T2254Z/`.
- Journal (append-only truth): `/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3`.

**Operate without an agent:**
- Progress: `tail -f <scratchpad>/full300_progress.log`; counted total:
  `sqlite3 "file:<journal>?mode=ro" "SELECT COUNT(DISTINCT session_id) FROM events WHERE event_type='audio_e2e.case_completed'"`.
- Hear any test: pick a WAV under `campaign_full300/**/segments/` and
  `pw-play --target <Jabra sink> <wav>`; its transcript:
  `SELECT json_extract(payload_json,'$.text') FROM events WHERE event_type='listener.final_transcript' AND json_extract(payload_json,'$.audio_path') LIKE '%<file>%'`.
- Resume after a crash: re-run the Phase 3 command in this file's §"bulk launch"
  (recorded in the supervising agent's report + scratchpad shell history);
  state file resumes; blocked cases stay parked.
- After campaign end: triage blocked cases from their `failure_bundle` fields in
  `full300_state.json`, fix, reset only those cases' stage/bundle, re-run.

**Key defect classes fixed en route (all committed):** phonetic WER equivalence;
decode-budget truncation; per-case continue-on-failure (head-of-line starvation);
capture retry taxonomy (WER/timeout/partial chains); echo-cancellation
(same-device loopback impossible on Jabra); C920 VAD noise floor; event-driven
post-wake handoff + fail-closed no-speech gate (Whisper hallucination);
48 kHz monitor capture resampling; clone-mode chat projection
(source-qualification speaker slot, restricted-memory chain, accepted-chain
anchoring).

**Timestamp**: 2026-07-18T12:45:00Z
**Active Agent**: Claude (Opus 4.8)
**Supersedes**: 2026-07-17T20:55:00Z handoff (root cause in that document was wrong — see §3)

## 0. UPDATE 2026-07-18T15:30Z — FIRST COUNTED E2E CASE COMPLETE (count 0 -> 1)

Case `sparta_qra_compliance-simple-01` (2 turns, `physical_live_horus`, live human at
Jabra) completed end-to-end: session `embry-e2e-046b755cb3733f4f457e0834-...-a02`,
seq 1-125, all events `mocked=0 live=1`. Full spine journaled including the three
formerly producer-less events: `speaker.verification.completed` (live scores
0.9208/0.9261, margins ~0.274 vs threshold 0.75/0.08), `tau.turn_plan.completed`,
`chatterbox.voice_render.completed`. State: scratchpad `one_case_state_LIVE_a02.json`
`status: completed`. §4's "no producers" and "count 0" are now RESOLVED.

Changes landed in `agent-skills@main` (emitters merged `fa07a7c5b`; fixes
`002ab7239` recover live human wake, `1da4c6106` `--attempt N` compile flag,
`215fec986` `CHATTERBOX_HOST_OUT_DIR` render path). Container rebuilt/redeployed
twice from main (`current-20260718`, `-r2`); listener service byte-identical to old
image, journal DB intact throughout.

Operational notes for campaign scale:
- Runner runs HOST-side under `chatterbox/.venv/bin/python` with
  `PYTHONPATH=agent-skills/skills/embry-voice-control/src`; do NOT `uv run` (drops
  resemblyzer). `CHATTERBOX_HOST_OUT_DIR=/home/graham/workspace/experiments/chatterbox/logs`
  must be exported for render verification.
- Managed-listener socket must be a SHORT path (AF_UNIX 108-char limit), e.g.
  `/run/user/1000/embry-e2e.sock`.
- Managed listener persists cycle state in `<campaign-dir>/managed-listener/`; it
  leaks across attempts (a failed attempt consumes cycles). Needs a per-attempt
  run-dir fix before unattended bulk runs.
- Live human wake is TWO-STAGE (say "Hey Embry" alone, wait for accept, then the
  request); transcript-phrase matching needed ~3 tries per wake at seated distance.
  Synthesized campaigns use pre-qualified wake WAVs and skip this friction.
- This case's proof scope gates `no_playback: true` — the audible Jabra pw-play leg
  is still unproven in a counted spine; rendered WAVs are on disk, hash-verified.

## 1. Immutable Goal

E2E testing for the 200+ case audio-first stress campaign. Every counted case must traverse:

```text
Horus speech audio -> PipeWire capture -> RealtimeSTT -> Horus speaker gate ->
canonical SQLite journal -> Memory -> bounded Tau tick -> Chatterbox render ->
Jabra pw-play -> chat projection -> replayable journal
```

Typed prompts, mocked transcripts, and direct Chatterbox text calls do **not** count.
Spec: `.ask/embry-200-e2e-runner-architecture.md`. Matrix: `docs/EMBRY_STRESS_SESSION_MATRIX.json` (300 sessions).

## 2. Proven Today (live, non-mocked)

- **Full spoken loop, human voice through audible answer**:
  - wake `listener.wake_detected` seq 2313 (`hey_embry_v1`, native callback)
  - final `listener.final_transcript` seq 2329 "What is the capital of Japan?" (`mocked=0 live=1`)
  - `listener/latest` surfaced seq 2329 -> live-turn -> entities/intent QUERY/Brave (5 results) -> answerText
  - Chatterbox render -> `pw-play --target 65` (Jabra sink)
- **Automated physical playback fixed** — `physical_playback=true` returns HTTP 200; receipt
  `embry.voice.playback_started.v1` with `wav_sha256`, `owner_service: ux-lab-api.service`.
  Previously 502 "audio path not readable by ux-lab".
- **Horus speaker enrollment PASSES** with audio captured today:
  - receipt: `logs/horus-enrollment-jabra-20260718T123000Z/receipt.json`
  - held-out Horus: 0.9091 / 0.8613 / 0.9150 / 0.8967 — all accepted (threshold 0.75)
  - impostors rejected: `embry_chatterbox` 0.5673, `kai_kling` 0.6874
  - ambiguity margin 0.1739 (required >= 0.08)
  - corpus: `persona_dream_voice_refs/horus_corpus/jabra_20260718/` (8 segmented samples)

## 3. Corrected Root Causes (previous handoff was wrong)

- **Microphone was the blocker — specifically DISTANCE, not PipeWire and not hardware.**
  The prior handoff's stereo-downmix, ALSA-gain, and WirePlumber-remap thread chased a
  corruption that never existed. Evidence (Whisper + RMS, same speaker, same sentences):

  | Path | Distance | RMS | Whisper |
  |---|---|---|---|
  | C920 direct ALSA | 6-12 in | 4027 | intelligible |
  | C920 via PipeWire | 6-12 in | 3241 | intelligible |
  | C920 via PipeWire | seated | ~842 | empty (wake score 0.0004 vs 0.88 threshold) |

  PipeWire passes C920 audio cleanly. The C920 is a far-field webcam mic failing at
  seated distance; gain boost only amplifies its noise floor.

- **Mic shootout (all three captured simultaneously, same utterances)**:

  | Mic | Noise floor | Speech | SNR |
  |---|---|---|---|
  | C920 | 598 | 6536 | 10.9x |
  | **Jabra SPEAK 510** | **293** | **8426** | **28.8x** |
  | ALC1220 | 0 | 0 | nothing connected |

  **Jabra is the release microphone.** Sender now targets
  `alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback`
  (unit `embry-pcm-sender-jabra.service`). C920 retired from the spoken path.

- **ux-lab instability was a Node version fault, not the dirty pi-mono tree.**
  `login-shell-env.conf` ran `npx` under `zsh -lic`; `npx`'s `#!/usr/bin/env node` shebang
  resolved system Node 18.19.1, where `import.meta.dirname` is undefined ->
  `skillsCatalog.ts:15` crash. Fixed by pinning the Node 22 binary and tsx CLI by absolute
  path. Old config: `login-shell-env.conf.bak-20260718`. Result: `NRestarts=0`.
  A duplicate orphan process (pid 1719043) also held port 3001 without
  `CHATTERBOX_HOST_OUT_DIR`; killed, systemd unit now sole owner.

## 4. What Is Currently Broken (blocks the immutable goal)

- **The required journal event spine has NO producers.** Verified by exhaustive search:

  | Event type | Emitter |
  |---|---|
  | `speaker.verification.completed` | **none** (all hits are readers/guards/comments/tests) |
  | `tau.turn_plan.completed` | **none** |
  | `chatterbox.voice_render.completed` | only a manual backfill script, not wired live |
  | `playback.requested/started/ended` | real emitter in `pipewire_playback.py`, but it
    requires a prior `chatterbox.voice_render.completed` that nothing emits -> unreachable |

  The active journal contains **only** `listener.*` events (max sequence 2440).
  Campaign stop conditions are therefore currently unsatisfiable.

- **The cited baseline proof cannot be substantiated.** Session
  `physical-hot-mic-20260711T010233Z-2668d0b9` (the architecture doc's "proven canonical
  turn" with speaker/tau/chatterbox/playback lineage) **does not exist in any database or
  file on disk** — zero grep hits, no rotated/backup journals. Treat the truthful E2E
  count as **0**, not 1.

- **Repo fragmentation — RESOLVED 2026-07-18.** `agent-skills` was on feature branch
  `battle-ux8-live-contract`, 1368 dirty files, 225 commits behind main, and it was what
  the live service loaded. Migration performed:

  1. `git stash push -u` -> `stash@{0}` ("battle-ux8-live-contract WIP before main
     migration 20260718"). Preserves 4144 uncommitted lines incl. `audio_e2e/runner.py`
     (+2104) and untracked `prepare_clone_assets.py`. `.venv` is gitignored, so untouched.
  2. `git worktree prune` — **188 -> 33** worktrees. A stale registration for
     `/tmp/agent-skills-main-pro-reasoning` (directory long gone) was blocking checkout.
  3. `git branch backup-local-main-20260718` (= old local main `c37dc5cc0`).
  4. `git reset --hard origin/main` -> `bb767ed7e`, divergence now `0/0`.

  Safe because the 22 local-only commits already existed upstream under different hashes
  (rebased), verified by message match — e.g. local `28dc24822` == origin `ce7ad24fe`
  "Make Unix listener authoritative for Embry voice". The feature branch's uncommitted
  work was also *behind* main (main's `runner.py` 2374 lines vs 2183; `prepare_clone_assets.py`
  3104 vs 2786).

  **Post-migration health verified**: package imports OK, `audio_e2e` complete, Jabra
  sender active, RealtimeSTT `ready/pcm.connected/gap_count=0`, journal seq 2440,
  ux-lab `final_sequence 2439 live=true`, `NRestarts=0`.

  **Canonical is now `agent-skills` @ `main`.** Still-existing duplicates
  `agent-skills-main` and `agent-skills-adaptive-mechanics` (no `.git`) were left
  untouched and should be retired separately.

- **`resemblyzer` was never installed or declared.** Added to `chatterbox/.venv` along with
  `setuptools<81` (webrtcvad needs `pkg_resources`). Not yet added to `pyproject.toml`.

## 5. Next Steps

1. **Do not create mocked or unit-test substitutes.** Live/e2e only.
2. **Write the three missing emitters** into `agent-skills` @ `main` (canonical), modelled on
   `pipewire_playback.py` (uses `append_event`, `claim_event` leases, causation chain,
   `_event()` helper; see `event_journal.validate_event` for the contract):
   - `speaker.verification.completed` — wrap the resemblyzer gate now proven working
   - `tau.turn_plan.completed`
   - `chatterbox.voice_render.completed` — unblocks the existing playback emitter
3. **Rebuild and redeploy the listener container — editing the host tree is NOT enough.**
   The listener is NOT a host process. It runs inside container `embry-voice-journal-8032`
   from image `embry-voice-control:current-20260717` (built 2026-07-17T11:15 from the
   feature-branch tree). Port 8019 is *inside* the container, published to host 127.0.0.1:8032
   — which is exactly where RealtimeSTT posts (`EMBRY_JOURNAL_URL`). Its only bind mount is
   state (`/mnt/storage12tb/.../state -> /var/lib/embry-voice`); **code is baked into the
   image, not mounted**. Consequences:
   - The migration to `main` did NOT change what the live listener executes.
   - `docker restart` reloads the SAME image and changes nothing. (No `sudo` involved —
     an earlier version of this handoff wrongly claimed a root host process needing sudo.)
   - **Any emitter written into the host tree has zero live effect until rebuild+redeploy.**

   Deploy loop: edit `agent-skills@main` -> build `deploy/Dockerfile.voice-control` ->
   redeploy `embry-voice-journal-8032` -> verify loop.

   RISK: the first rebuild from `main` ships 326 unreleased commits into the component that
   writes the journal. Consider rebuilding from main FIRST and verifying the loop, before
   adding new emitter code, so a regression has one cause and not two.
4. **Qualify the Horus voice clone per tone.** Chatterbox conditioned on Horus reference
   audio (option 1 in the architecture doc). Resemblyzer embeddings shift with emotional
   prosody, so a neutral clone passing at 0.86 does **not** imply the frustrated/hostile
   variants clear 0.75. Qualify each tone separately; fail closed and record physically
   for any tone that misses. `audio_e2e/prepare_clone_assets.py` already exists.
5. **Label synthetic provenance permanently** so a synthesized case can never be relabeled
   as physical speech (explicit architecture-doc requirement).
6. **Two-tier campaign**: synthesized bulk + a small physical-human subset anchoring room
   acoustics.

## 6. Project Context

- **Chatterbox is an active fork** (`upstream git@github.com:resemble-ai/chatterbox.git`,
  real merge history). Do **not** relocate Embry orchestration into it — README correctly
  scopes it as renderer only, not listener/memory/UI authority. Keep the fork a thin delta.
- **Key files**:
  - `scripts/prove_physical_horus_enrollment.py` — speaker gate proof (threshold 0.75,
    margin 0.08, `speaker_id: horus_lupercal`); requires `.venv/bin/python`
  - `scripts/horus_capture_segment.py` — agent-driven capture: silence segmentation,
    Whisper alignment to expected text, level verdicts, retake decisions (NEW)
  - `scripts/record_horus_corpus.py` — corpus definitions and guided capture (NEW)
  - `agent-skills-main/.../embry_voice_control/event_journal.py` — `append_event`
  - `agent-skills-main/.../embry_voice_control/pipewire_playback.py` — emitter template
  - `pi-mono/packages/ux-lab/server/index.ts:11135` — `/out/` -> `CHATTERBOX_HOST_OUT_DIR`
- **Journal**: `/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3`
  (data only at that path; code lives in the agent-skills trees)
- **Claim boundary**:
  - `mocked: no`, `live: yes`
  - Proven: Jabra human wake/transcript, journal final, Memory/Brave answer, Chatterbox
    render, automated Jabra playback, Horus enrollment with impostor rejection.
  - **Not proven**: human-audible witness (playback exit 0, but no human confirmation
    recorded), full journal lineage (3 of 6 event types have no producer), any clone
    qualification, any counted E2E case.

---

## 2026-07-19 — Full 300-case audio E2E bulk campaign (silent PipeWire loopback tier)

**New campaign id:** `campaign_bf26de7573167482301d887e` (all 300 stress-matrix cases,
`qualified_horus_clone` source mode). Ran unattended overnight through the silent null-sink
loopback (`embry_horus_input`); **no audio to any hardware sink** — verified zero
`alsa_output.*` stream targets throughout. All playback via `pw-play --target
embry_horus_input`. No WER/phonetic thresholds, spine services, or acceptance code altered.

**Headline result (journal-counted, `audio_e2e.case_completed` distinct sessions):**
- **247 / 258 asset-backed cases completed** full-spine, live E2E.
- Journal shows **79,520 events, all `live=1 mocked=0`** for the campaign (zero mocked).
  Per-turn spine complete: 845 each of `audio_source.qualification.completed`,
  `memory.answer_resolved`, `tau.turn_plan.completed`, `chatterbox.voice_render.completed`,
  plus 845 `memory.synthetic_source_restricted` (synthetic clone provenance correctly
  blocked from personal Memory; `speaker_identity_proven:false`, `allow_personal_memory:false`).

**Two-stage funnel:**
- **Phase 2 (asset gen/qualification, Orpheus GPU, ~11.5h):** 865 unique qualified query
  assets across 258 cases (WER ≤ 0.25, internal silence < 2.0s). **42 cases asset-blocked** —
  ASR qualification exhausted (2 fresh 5-candidate rolls) on hard content: mostly
  `skill_create_evidence_case` (15, CAE/Claims-Arguments-Evidence jargon), `persona_memory_miss`
  (7), `factory_noise` (5), `tone_emotion` (5), `sparta_qra_compliance` (3). Content-specific,
  not systemic; the locked WER ceiling correctly rejected marginal synthetic audio.
  Assets manifest: `logs/horus-clone-assets-full300-20260718T2254Z/qualified-horus-clone-assets.json` (status PASS).
- **Phase 3 (live campaign run, listener float16 cuda, ~10h):** of the 258 asset-backed cases,
  247 completed, **11 spine-blocked** — 8 listener-tier content failures
  (`listener_receipt_missing` / `managed_listener_request_wer_exceeded` on adversarial/soak
  utterances), 2 `entity_span_mismatch` at chatterbox render (genuine downstream defect, matches
  pilot Row 5), 1 `extract-entities` tooling failure on D-Bus jargon. All content-specific/known
  downstream — none systemic.

**One transient systemic event handled:** `chatterbox-fork-agent-server` self-restarted ~20:47Z,
causing a cluster of 12 `chatterbox_render_command_failed` httpx ConnectErrors that parked 12
cases. Diagnosed from artifacts (container uptime + httpx `map_httpcore_exceptions`), confirmed
chatterbox healthy again, and did **one deliberate retry** of exactly those 12 (receipts intact,
render-only) — **all 12 recovered**. Chatterbox not modified (protected spine service).

**One environment fix (operational, no code change):** Orpheus returned a CUDA device-placement
error (`index on cuda:0 vs tensors on cpu`) at inference because GPU was full (~24/24.5 GB) and
accelerate offloaded the embedding to CPU at load. Freed idle voicemode GPU services
(`voicemode-whisper`, `voicemode-kokoro`) and restarted `orpheus-infer` so it loaded fully on
GPU → synthesize PASS. Voicemode services **restored** at campaign end; Orpheus left stopped
(matches its pre-campaign state).

**Commits / branch pointer:** none — no code defect found; all failures were content-specific,
a protected-spine transient, or environment/GPU contention. `voice-campaign-20260718` pointer
unchanged.

**Overall counted tally (this campaign + prior evidence):** 247 (full300) + pilot campaign
`campaign_7af1cf` (12 cases through the loopback listener tier; 8 full-spine completed, 4 parked
at render as Row-5 downstream defects) + 1 physical Jabra case = new counted full-spine E2E
completions dominated by the **247** in this campaign.

**Key state/artifacts (scratchpad `…/8928d5f2-…/scratchpad/`):** `full300_manifest.json` (300),
`full258_manifest.json` (asset-backed run set), `full258_state.json` (run state; 247 completed /
11 blocked), `full300_progress.log` (tail-able heartbeat), `prepare_supervisor.py` /
`run_supervisor.py` (bounded resume supervisors), `asset_blocked_42.json`. Runner behavior
learned: the run does **up-front audio-asset validation for every manifest case and fails closed**
if any case lacks assets — so asset-blocked cases must be **excluded from the run manifest**, not
left in it (hence the 258-case run manifest).
