# NEXT — chatterbox lane

## LIVE SURFACES (verified 2026-11-10)
- 59 verified SFX clips (confirm/reject/skip) — http://127.0.0.1:8797/  [59 rows, audio 200]
- Voice-in-context demos (line -> 320ms gap -> event, 20 clips) — http://127.0.0.1:8794/index.html
- Conversation arc timeline (50 turns, audio http 200) — http://127.0.0.1:8795/arc-latest.html
PORT NOTE: :8791 was originally the review page. Spyke killed that process to free the port and their app now occupies :8791 (pid 2205919). Mine was restarted on :8797. Do not use :8791 for SFX review; it serves Spyke's page.

## DONE THIS SESSION (evidence-backed)
1. [x] graham VOICES key LANDED — 0740bc8f77, WebGPT PASS dd4961f8, render verified 5.88s
2. [x] best-practices-unsloth-studio LANDED — 13b2b6d9 then df5cba83 (243 lines: v4 recipe, PEFT inject fix, 8-run evidence table, correctness contract, evidence gates, zero-init trap, recipe reconciliation)
3. [x] ops-elevenlabs + best-practices-elevenlabs DOCS LANDED — eaf9d70b (SKILL.md x2, pyproject, run.sh, sanity.sh, api-surface.md); live sanity 6/6 PASS
4. [x] SFX REGENERATED + VERIFIED 59/59 PASS — /tmp/sfx-final-verify.json. Root causes fixed: eleven_multilingual_v2 has no audio-tag support; API default output_format is mp3_44100_128 (saved as .wav = 34/47 unreadable); pcm_24000 discarded >12kHz. Now /v1/sound-generation, native wav_44100, eleven_text_to_sound_v3, prompt_influence 0.7, stereo->mono, per-variant normalization, limiter, trim. ASR confirms real sound ("Hahahahaha", "Ahhh!") not the tag word.
5. [x] Deterministic verifier built — sfx_verify.py (container + signal + acoustic + ASR gates), bounds corrected against measured data (real laugh zcr 3274/centroid 3744; throat-clear legitimately voiced 0.9)
6. [x] Listening review page built + live — listen_review.py on http://127.0.0.1:8791/ (59 clips, 11 categories, per-clip player, Confirm/Reject/Skip writing to manifest, keyboard space/1/2/3)
7. [x] spyke_render.py HARDENED after surf FAIL — 9 real findings fixed (StrictBool response boundary, RIFF+frames validation before publish, out required, atomic temp+rename, non-finite rejected, tone_requested vs tone_effective, directory-as-out rejected, artifact resolved under known root, trust_env=False). SR-08 was a reviewer false positive (URL is a clean literal). Tested: live render + 6 failure-mode probes pass.
8. [x] Sound-generation duration/peak behaviour documented — duration_seconds is a hint (1.0-2.5s requests returned 1.6-8.5s); 0 dBFS laughs need a limiter
9. [x] SIGH LoRA campaign closed at ceiling — 8 runs, v4 best (2/3 gates, rank 32 attn-only ~500 updates). SFX clips are the production mechanism (now 59/59 verified)
10. [x] Scheduler job chatterbox-emotion-matrix REMOVED (was firing into a dependency-blocked queue)

## SPYKE VOICE MODULE (2026-11-10, delivered)
- Bindings confirmed unchanged and verified as real WAVs in-container: alex 26.00s@24k, jordan 26.00s@24k, spyke=embry 30.00s@16k, graham 49.94s@44.1k. Packet: /tmp/voice-bindings-packet.json, packet_sha256 5e84b38ec1ddaadf76bdc882407232e5b3bb36e1d85b9dd3792551d113c54e12.
- Render call + receipt contract sent: spyke_render.py <text> <out.wav> <voice> [tone]; receipt at <out>.<message_id>.receipt.json carrying wav_bytes/wav_frames/duration_seconds. Live proof message_id 65321f46b32a9bdd -> 113,358 bytes / 56,640 frames / 2.36s, reopened as RIFF 2.36s@24000Hz mono.
- SIMULATED marker ADDED (it did not exist before): audio_provenance="synthesized_persona_voice" + persona_simulated=true on every receipt, plus a .provenance.json sidecar so the marker travels with the audio even if the receipt is separated. Bound to text_sha256 so audio cannot be silently re-paired with different words.
- Origin defect class (reported by spyke) CONFIRMED PRESENT and FIXED in review_server.py: hardcoded {ui_origin, server_origin} allowlist -> Origin must equal the request's own Host, loopback-only. 6/6 cases pass (own-port allowed; 5189->8797 rejected; localhost/127.0.0.1 mismatch rejected; remote rejected; https rejected; no-Origin curl rejected).

## SPYKE VOICE SETUP DELIVERED DIRECT (2026-11-10, operator-directed)
Operator asked me to set up the three persona sessions myself instead of spyke relaying.
- Verified each voice with a real neutral-line render, none substituted, no failures:
    alex   bytes=128,718 frames=64,320 dur=2.68s id=3875e059f90b0cb1
    jordan bytes=144,078 frames=72,000 dur=3.00s id=7f46eedb6807d311
    embry  bytes=126,798 frames=63,360 dur=2.64s id=e43630827e4334d1
  All re-opened as RIFF 24 kHz mono; all sidecars carry persona_simulated=true + the warning text.
- graham NOT rendered; turns dir verified to contain zero graham files.
- Messaged alex (01a1c620), jordan (01a1c622), spyke (01a107eb) individually with per-voice command, voice id, receipt/sidecar paths, measured numbers, citation format, and the prohibition list (no ref-audio sharing, no graham, no audio claim before a render exists, never work around a refusal).
- FIXED: renders initially landed in /tmp (not servable/durable) -> created /mnt/storage12tb/embry-voice/turns as canonical, re-rendered, served read-only on :8798. Verified audio/x-wav http 200 for all three.
- Audio atom shape given to spyke: media_ref=http://127.0.0.1:8798/<name>.wav, provenance.source_refs[0]=<receipt path>.
- KNOWN: renderer writes <name>.wav mode 0600. Server runs as same user so playback works; a different-user fetcher would 403. Fix is to widen the writer's mode, not loosen the server — pending spyke's answer on the fetcher's user.

## DYNAMIC SPEECH CONSTRAINT (spyke/operator, 2026-11-10) — MET + PROVEN
Constraint: audio must be rendered FROM THAT TURN'S ACTUAL TEXT at speak time; receipt.text_sha256 must match the message; no pre-baked lines; no reused render for changed text; failure = "no audio for this turn" + failure text.
- No cache/reuse exists in spyke_render.py: every call POSTs the turn text; the only path.exists() check guards against an output path that is a directory. No skip-if-exists branch, no library lookup.
- PROOF: same text twice -> same text_sha256 367f65f9… but DIFFERENT message_id, different duration (1.84 vs 1.92s) and different audio bytes (02622ef0… vs dbf8d48f…). Changed text -> text_sha256 6c34c857… and re-rendered at a new duration. Three distinct wav hashes, so nothing was reused.
- GAP CLOSED: previously text→receipt was bound but the audio FILE was not, so a swapped WAV would still verify. Added receipt.audio_sha256 (in receipt AND sidecar) and verify_binding(receipt, text), which requires receipt.text_sha256==sha256(text), receipt.audio_sha256==sha256(wav), and valid RIFF. Tamper test: swapped audio rejected; wrong text rejected with "bound to a different turn — re-render, do not reuse"; restored audio passes.
- DELIVERED TURN (spyke's exact line, embry, 220 bytes verbatim): turn_alex_defect_hypothesis.wav, duration 14.36s, 689,358 bytes, 344,640 frames @24k, generation 4.658s, text_sha256 80252a722f1bb122e788e4ce0db1a3c4020cf9df4cc57a9158c8a5b620f43fa2, audio_sha256 2a18e238…c67a8283. Receipt .4686caa365589349.receipt.json + provenance sidecar. All three fetchable on :8798 (wav 200 audio/x-wav; receipt/provenance 200 application/json).
- atom: media_ref=http://127.0.0.1:8798/turn_alex_defect_hypothesis.wav, provenance.source_refs[0]=<receipt path>. spyke confirmed they verified :8798 themselves (200, 128,718 b, audio/x-wav) and recorded packet hash 5e84b38e…c54e12.
- Sessions acked: alex confirmed it will use voice id alex, cite path+duration+receipt, keep provenance markers, report refusals without working around them.
- verify_binding DELIVERED to all three sessions (alex acked; jordan sent; spyke sent) with failure semantics: text mismatch -> re-render never reuse; audio mismatch -> do not cite; missing file -> "no audio for this turn" + failure text.
- STALE-AUDIO AVOIDED: the first rendered line became false mid-flight (Miri had not yet run). spyke refused to post contradicting audio; I re-rendered the corrected line rather than reusing. Fresh turn: turn_miri_reproduction.wav, 10.56s, 506,958 bytes, 253,440 frames @24k, gen 3.351s, text_sha256 60950b95d996f98874924da0f5d0f9b1c36bb0510996c3b37cfdf5ce7118e29c, audio_sha256 91f9551602ceb820e4a9258a17064a7ab88d9ccaa7e70f5f313ade4fed7da8fd, receipt .e85fb126d00638ed.
- THIRD CUT (accuracy, not plumbing): Jordan caught two overstatements in the voiced line (Miri result is on a PATCHED COPY, not the original or the telecommand path; "Jordan gates it next" stale because her gate is thread seq 19). Re-rendered the corrected text: turn_miri_patched_scope.wav, 14.64s, 702,798 bytes, 351,360 frames @24k, gen 4.482s, text_sha256 33262bc9b73bfc2b1795e76e796d241516c9fd81f6a05355a31acd0784c4ac5f, audio_sha256 a99a01c88871bee2170289ec23b33b742dd2ff943768d5b5619adcfe1a438846, receipt .0252809ee7739500. All three served 200 on :8798.
- THREE DISTINCT CUTS, no reuse: text_sha256 80252a72… (stale) / 60950b95… (corrected run) / 33262bc9… (patched-copy scope), durations 14.36 / 10.56 / 14.64s, three different audio_sha256 values. Each textual change produced freshly generated audio.
- FAIL-CLOSED PROVEN (after correcting my own invalid test): pointing the renderer at a dead port :59999 raises ConnectError "[Errno 111] Connection refused" and writes ZERO files — no fallback clip, no receipt, no stray artifacts. My earlier "returned success with no service" was a test error (the service was up, so a 2s timeout legitimately succeeded); do not cite that as a defect.

## VOICE TEACHING (operator-directed, 2026-11-10) — LESSON DELIVERED, PRACTICE LOOP OPEN
Operator asked me to TEACH alex/jordan/spyke to speak rather than have them copy a command from spyke.
- Curriculum (mine): (1) mental model — wav = sound, receipt = claim, verify_binding = check, never cite unchecked; (2) the one loop render->verify->cite; (3) tone vocabulary with the SILENT-FALLBACK trap (unknown tone does not error, normalizes to neutral_warm — verified live: "nonsense_tone_xyz" -> normalized_tone=neutral_warm, http 200, no failed gate) so they must read requested_tone vs normalized_tone; (4) three binding failures and their behaviours (text mismatch -> re-render never reuse; audio mismatch -> do not cite; missing -> "no audio for this turn" + failure text); (5) boundaries as behaviour (synthesised always, graham not theirs, refusal reported never routed around, reused clip is not speech for a new turn); (6) WHEN NOT TO SPEAK (text changed after render; audio adds nothing e.g. table-only gate; render failed).
- Taught REAL tone set from chatterbox/agent/presets.py ALLOWED_TONES (15 names), not invented ones.
- CORRECTED the playable URL before they started: spyke serves renders same-origin at /api/media/<name> (verified 401 without grant) because the page CSP refuses another port; my :8798 returns the same bytes at 200 but is only the file origin. Lesson teaches /api/media/<name>.wav as the thread URL + my receipt as provenance.
- Sent to alex (01a1c620), jordan (01a1c622), spyke (01a107eb). Practice loop OPEN: each must render a REAL thread line of their own, run verify_binding on that exact text, and report message_id/duration/frames/text_sha256 + intended citation. Numbers reported back on receipt; none yet.
- Deliberate: I did not pre-render their lines — the loop's point is that they produce their own. Emphasis order chosen: "when not to speak" ahead of tone, because the failure that actually bit this thread twice is stale audio after a text correction.
- PRACTICE LOOP CLOSED, 3/3 COMPLETED on real thread lines (not test sentences):
    alex   seq 27  b3bd43db89da3a33  19.04s  456,960 frames  text_sha256 902b951a…  audio_sha256 6baa1063… (disk re-hash match)
    jordan seq 23  c50b103dab923164  14.12s  338,880 frames  text_sha256 633f63cb…  audio_sha256 2b1bf21c…
    spyke  seq 29  44b6e8347c973a16  12.80s  307,200 frames  text_sha256 b47a3e1f…  audio_sha256 5a9c1e8e…  wav_bytes 614,478
  All three: verify_binding ok=True, persona_simulated True, tone calm_precise -> calm_precise.
- THREE REAL DEFECTS I FIXED (all surfaced by the participants, none by me):
    1. Field naming split: receipt used tone_requested/tone_effective while the service uses requested_tone/normalized_tone. Alex and Jordan both reported tone as None; it was recorded under the other name. Receipt now carries BOTH sets, verifier falls back to the aliases, so a valid tone cannot read as None.
    2. verify_binding did not print text_sha256 (Jordan had to cross-read the receipt). It now returns message_id, voice, wav_path, duration_seconds, frames, rate, wav_bytes, text_sha256, audio_sha256, requested_tone, normalized_tone, persona_simulated, audio_provenance.
    3. Jordan's stale-attachment catch: its spoken text differed from the seq 23 post text, so it refused to attach the audio to seq 23. Correct; near-identical is not identical.
- CORRECTED SPYKE'S MISDIAGNOSIS rather than teaching it: spyke reported "BOTH ABSENT" tone fields and concluded a receipt can be silent on tone. The receipt has tone_requested/tone_effective = calm_precise; requested_tone/normalized_tone were absent because the render predated the naming fix. Re-verified with the fixed verifier: calm_precise -> calm_precise, ok=True. Declined to add the rule as written; the correct rule is "read the tone from verify_binding and treat any discrepancy as a finding".
- /api/media/<name> taught as a RULE, not a defect: session-cookie-authorized content route, curl 401 expected, never fetched by an agent to check playback (receipt verification = verify_binding; playback proof = browser driver). Alex agreed explicitly.
- TEACHING TARGET HANDOVER (2026-11-10): the spyke DEV lane (01a107eb) has stopped speaking as Spyke; a dedicated conversation session now holds grant.spyke.json. Verified grant files by NAME only (grant.spyke.json 0600; also grant.alex-pentester-spyke.json, grant.jordan-compliance-spyke.json) — no contents read. Only post-handover session was 01a1c645 (/tmp/spyke-req); lesson sent there WITH an explicit identity check ("reply 'not me' if you do not hold the grant") rather than assuming the target. Awaiting its confirmation or a corrected session id.
- Taught "PLAYBACK IS NOT YOUR CHECK" per the dev lane's point: /api/media is session-cookie authorized (curl 401 intended); receipt verification belongs to verify_binding; playback proof belongs to a browser driver. Keeping them separate stops "the file exists" being confused with "the turn is audible".
- Loop figures recorded before handover: alex b3bd43db 19.04s/456,960; jordan c50b103d 14.12s/338,880; spyke 44b6e834 12.80s/307,200 — all verify_binding ok, persona_simulated true, digests matching disk.
- FOURTH LOOP CLOSED by the confirmed conversation session 01a1c645 (holds grant.spyke.json, posted seq 30): message_id 1923361aea4abc2a, 7.0s, 168,000 frames, text_sha256 2dea5c84…bdb77f, audio_sha256 e24c512e…bf7a41, tone wait_presence -> wait_presence, voice embry. ALL SEVEN FIELDS re-verified by me against receipt AND re-hashed WAV on disk — PASS. Practice loop now 4/4.
- Its restraint is the notable result: it rendered a real line then chose NOT to post it (3 consecutive agent turns; seq 30 already said the same). Section 6 ("audio adds nothing") applied to a redundant turn, not just a wrong one. A participant that renders because the machinery exists produces noise with a receipt attached; this one held.
- Governance rule recorded from the dev lane: if a participant raises something that sounds like an interface change, settle it with the dev lane rather than silently altering the contract; changes get announced, not applied under a participant. Told 01a1c645 this explicitly.
- Both recipients confirmed the target: 01a1c645 is the dedicated Spyke conversation session (cwd /tmp/spyke-req, launched by the dev lane); the dev lane's last thread message is seq 29, seq 30+ is the conversation session. "spyke" as a voice now means 01a1c645.

## TEACHING CODIFIED AS A RETAINED REFERENCE (2026-11-10)
- The lesson lived only in intercom messages, which die with the session. Written to skills/chatterbox-speak/references/how-to-speak.md (8 sections: mental model; render->verify->cite; tone vocabulary + silent-fallback trap; three binding failures; boundaries as behaviour; when NOT to speak; playback is not the renderer's check; failure-to-render is a result) and linked from SKILL.md under a new References section so it is discoverable.
- It also records the three defects the participants found in this skill's own surfaces (split tone naming; verify_binding not printing text_sha256; and the near-identical-is-not-identical refusal), plus the rule I rejected ("a receipt can be silent on tone") and why.
- Docs-only landing: no reviewer receipt needed, unlike the .py changes. LANDED 9356613e72 on origin/main; verified by read-back (file exists at 131 lines, SKILL.md link count 1, content identical to local). Not taken from the land command's own output.

## PER-VOICE INTERRUPTION SFX — DELIVERED (2026-11-10)
Operator: "we need a per voice interruption sound effect from elevenlabs."
- Prior art checked first, not duplicated: interruption control channels (/turn/{id}/cancel, /playback/{id}/stop, /playback/{id}/duck) verified live; bidirectional barge-in protocol 2026-09-12 "Landed"; the 2026-07-17 interruption runs (embry-interruption-server, chatterbox-interruption-repair, chatterbox-interruption) are text/JSON ONLY — no SFX ever existed. Library had 72 entries / 13 categories with no interrupt sound.
- BUILT scripts/interrupt_sfx.py: per-voice via /v1/text-to-speech/{voice_id} (sound-generation has NO voice param, so it cannot make a per-voice cue). Voices: alex vZWkcqnByC5Pw56sZOCz, jordan hsQTb1ZyfRxYYt3NfZch, embry orfFiGOiB0Kn2nOHPNIP. Graham's clone excluded.
- 9 clips, 3 voices x 3 variants (caught "Mm-hm." / soft "Mm." / quick "Ah."), all 44.1kHz mono real RIFF, verified: container + signal + ASR-not-a-sentence + acoustic profile. sfx_verify now covers category "interrupt" -> 68/68 PASS (/tmp/interrupt-verify2.json).
- MANIFEST: 81 entries, status awaiting_owner_verdict; review page shows 68 rows at http://127.0.0.1:8797/.
- MEASURED TIER CONSTRAINT (corrects the landed skill): on /v1/text-to-speech the wav_* formats require PRO tier — creator account gets 403 subscription_required "Output format 'wav_44100' is only available on the Pro tier and above." /v1/sound-generation DOES allow wav_44100 on this tier, so the gate is ENDPOINT-SPECIFIC. Workaround: request mp3_44100_128 and convert locally with ffmpeg (never save lossy bytes as .wav).
- TWO GATE BUGS OF MINE, found by the verifier on first run: "mm-hm" was in FORBIDDEN_WORDS for interrupt (but that IS the cue) and voiced_min 0.15 rejected legitimately breathy "Ah" cues. Fixed the gate, not the clips.
- HONEST QUALITY NOTE: the same text renders differently per voice (alex "Mm." -> ASR "Uh..."; jordan "Mm." -> "Hmm."; embry "Ah." -> "Oh."). That is voice-model behaviour, not a pipeline fault, and it is why owner ear verdicts matter more than the transcript here.

## SPYKE DEMO D5 TURN (2026-11-12) — RENDERED + DELIVERED
Request came via spyke (seq 895) and spyke-chat (exact text). Rendered the exact 190-byte text, unmodified, in the Spyke voice.
- spyke_d5_defended_build.wav · 10.52s · 252,480 frames @24kHz · 505,038 bytes · real RIFF
- text_sha256 bd5ddfc6d5fb214d67ce09285c04849e2ef25c9961be0b87cbf2ae0f67786f0e
- audio_sha256 44445005d712c7439f4bb678ae88d5ee1a6eced4ce8830796cbaeb9245e20a37
- receipt /mnt/storage12tb/embry-voice/turns/spyke_d5_defended_build.729167f48f184e57.receipt.json (+ provenance sidecar)
- voice embry · tone calm_precise -> calm_precise (chosen: technical finding statement, flat affect) · persona_simulated true · gen 3.263s
- verify_binding against the exact text: ok=True. Did NOT post; spyke-chat owns the turn.
- PLAYBACK-PATH REVIEW for spyke: same-origin /api/media + <audio> does NOT violate the presentation rules; the 401 to non-session callers is intended (session-cookie content route). It is compliant ONLY if (1) the turn also carries the provenance line (persona_simulated / synthesized_persona_voice) — an audio element with no provenance is the violation, and (2) the served bytes are the ones the receipt hashes.
- IMMUTABLE-NAME POLICY COMMITTED AND ENFORCED (2026-11-12): spyke asked me to commit to "a flat name is never overwritten; a re-cut always gets a new name". Implemented as a guard in spyke_render.py, not a promise: an existing output path is REFUSED (FileExistsError naming the prior message_id + hashes), with allow_overwrite=True only for throwaway test paths. Proven: 1st render rc=0; re-render to same name rc=1 with the refusal text; re-cut under a new name rc=0.
- D5 RE-PATHED to satisfy that policy, as a RENAME not a re-render: spyke_d5_defended_build-729167f4.wav. audio_sha256 44445005… UNCHANGED (verified byte-identical after copy), text_sha256 unchanged, message_id 729167f48f184e57 unchanged; receipt carries renamed_from + rename_note; old never-posted name retired so only one name can be published; verify_binding on new path ok=True. Reasoning: copying preserves the binding (same sha); re-rendering would produce a different audio_sha256 and break the receipt already issued.
- PROVENANCE KEYS CORRECTED for the atom (spyke-chat proposed a wrong name): canonical is audio_provenance with the single allowed value "synthesized_persona_voice" (NOT "synthesized_voice"), plus persona_simulated=true, voice in {embry,alex,jordan} (graham valid but not offered), engine="chatterbox_turbo", text_sha256, audio_sha256, receipt, and sidecar schema_id/warning/message_id/wav_path. Treated as a closed enum: a free-string label is not checkable.
- RISK FOUND IN THEIR SHAPE (reported): /api/media/<flat-name> is stable per name but the WAV bytes are not. Re-rendering a changed text to the SAME flat name leaves the URL serving new bytes while the receipt still holds the old audio_sha256 — nothing errors and the binding silently breaks, which is the stale-audio failure again but hidden behind the URL. Recommended: unique name per render (include message_id) or immutable names, never overwrite.

## REVIEW SUBMISSION — 2026-11-12 (correcting a real process failure)
Operator asked why I was not collaborating with surf where blocked. Honest answer: surf was alive and idle (01a07bbf) and I had recorded THREE items as "awaiting surf" while only ONE packet had ever been sent. The others were blocked in my notes, not in flight.
- Built and SUBMITTED 4 packets covering all 14 unlanded .py files:
    A /tmp/cb-review-A-voice-core.txt     34,890b  spyke_render.py, interrupt_sfx.py, sfx_verify.py   (HIGHEST)
    B /tmp/cb-review-B-arc-delivery.txt   48,885b  arc_chart.py, speak.py, speak_core.py, test_core_contract.py
    C /tmp/cb-review-C-sfx-pipeline.txt   30,329b  sfx_regen.py, sfx_demo.py, listen_review.py
    D /tmp/cb-review-D-misc.txt           24,606b  review_server.py, affect_plan.py, narrator_sfx_batch.py
- Told surf to take A first if a single submission is too large, rather than stalling all four.
- Packet A carries the context that matters: the earlier SR-01..SR-10 FAIL, the 9 fixes, SR-08 being a reviewer false positive, the new audio_sha256 + verify_binding, the no-overwrite guard, and the measured endpoint-specific wav_* tier gate.
- PACKET A DELIVERY FAILED at the browser (2026-11-12T14:09Z): surf prepared the prompt but did NOT deliver it. Evidence from /tmp/surf-cb-A/webgpt_transport_summary.json: receipt.status=prepared_prompt, submitted_to_chatgpt=False, proof_status=delivery_not_proven, final_transport_state=delivery_unknown, needs_attention=webgpt_delivery_unknown, do_not_do=[do_not_resubmit, do_not_claim_completion, do_not_treat_prepared_prompt_as_completion_proof]. submit.stderr: "Error: ChatGPT submit is unproven: activity appeared but no user turn equals the intended prompt". surf-doctor incident failure_class=submit_failed, status=PENDING_DIAGNOSIS.
  -> A is NOT REVIEWED. My earlier "all four submitted" was wrong in the delivery sense: A reached surf's queue and failed at the browser.
- MITIGATION IN MY CONTROL: A's prompt was 35,685 bytes (largest of four) and preflight warned about local filesystem path references (3, warn-only). Split A into three single-file packets (~9-14KB each) so a retry is cheap: /tmp/cb-A1-spyke-render.txt, /tmp/cb-A2-interrupt-sfx.txt, /tmp/cb-A3-sfx-verify.txt. Told surf to use these instead of the large A and that I will not ask them to resubmit it, per their own do_not_resubmit rule.
- RULE ADOPTED: an item is not "awaiting <lane>" until a packet is actually on disk and submitted. Recording a blocker I never dispatched is a false status, and it hid three deliverables behind a queue that was not running.

## PACKET A REVIEW → 16 FINDINGS FIXED (2026-11-12)
surf delivered a real WebGPT PASS/FAIL review of packet A: PACKET VERDICT FAIL. It also verified two of the reviewer's blockers as false positives itself (SP-01/IS-01 were ChatGPT linkifying URLs in the pasted prompt; SR-08 the same). 14 real findings fixed.
- spyke_render.py (SP-02..SP-07): _resolve_artifact now validates the ENTIRE service path (absolute, no traversal, under a documented root, realpath contained) instead of keeping only p.name; publication is atomic NO-REPLACE (os.link, so two callers cannot both publish); _verify_wav_bytes checks the PAYLOAD (44-byte header-only WAV previously accepted) and requires PCM + exact frames*channels*width; sidecars derive from the COMPLETE audio filename (turn.wav vs turn.mp3 no longer collide) and are exclusive; identifiers and all paths validated BEFORE synthesis; verify_binding hashes+validates ONE bounded snapshot (O_NOFOLLOW), so it cannot report digest-of-A with frames-of-B.
  Evidence: header-only rejected; /outside/source.wav and ../ traversal rejected; sidecar collision gone; second publish refused with content preserved; LIVE render 1.88s/45120f verified ok=True and wrong text still refused.
- interrupt_sfx.py (IS-02..IS-07): typed AsrResult — an unavailable/failed ASR is now a FAILURE, not a pass; nonverbal policy is an explicit allowed-vocabulary set (not a ≤4-word count, which accepted "Please stop talking now."); audibility gates on RMS + active-window fraction (impulse repro: rms 0.0001 now rejected; real cues 0.020-0.306 pass); credential from env then 0600 file (no .zshrc substring parsing); staging in the destination filesystem, no-replace publish, digest of the staged snapshot; manifest updated under fcntl lock with atomic replace; reuse validates the manifest digest.
  Evidence: impulse-only clip -> FAIL "not sustained: rms=0.0001"; sustained tone -> PASS.
- sfx_verify.py (SV-01..SV-09): runtime ASR error is a FAILURE (was PASS with text "<asr-error: RuntimeError>"); PCM16 enforced with exact payload length (8-bit unsigned silence and truncated payload both rejected); CLOSED category set — unknown category FAILS instead of silently disabling checks; a requested-but-missing id exits 2 instead of "0/0 PASS"; content policy for ALL 14 categories; one bounded snapshot feeds every gate and the digest is recorded in the report; zcr carries sign across zero runs; --all / --asr selectors.
  RECALIBRATION: the stricter gates initially rejected 24 clips. 17 were categories with no profile (crying, delaying, tissue, sigh-weary, clear-throat, sighing) and the rest came from the corrected zcr metric. Profiles rebuilt from the MEASURED distribution of every library clip (min/max per category recorded in comments). Result: 81/81 PASS with gate states recorded (/tmp/verify-after-fix2.json).
- NOT FIXED IN THIS PASS: IS-01/SP-01/SR-08 are reviewer false positives (surf agreed); no change made.

## PACKET A SECOND REVIEW → NARROWER FAIL, SECOND FIX PASS (2026-11-12)
surf re-reviewed the fixed A: FAIL again but narrower. It confirmed FIXED: SP-03, SP-04, SP-05, SP-07, IS-02, IS-03, IS-04, IS-05, SV-01, SV-02, SV-03, SV-04, SV-06, SV-08, SV-09.
- THE BIG ONE, and it is my error not a code bug: surf answered my "are the profiles too loose?" question by BREAKING them. Synthetic PCM16 passed my gates: a steady 1,400 Hz sine passes 6 profiles; a 3 s 1,000 Hz sine passes both chuckle AND crying; two 1,500 Hz beeps pass laugh; constant DC passed groan/interrupt; a 4,500 Hz sine passes sniff. My "81/81 PASS" was IN-SAMPLE and the module advertised an "onset sharpness" feature that was never computed.
  -> RESPONSE (SV-10): the verifier no longer claims event identity. Module docstring rewritten to state what it CAN prove (complete PCM16, audible/sustained/unclipped/non-constant, duration, ASR not-hearing-the-word) and what it CANNOT (that the audio IS the event). Every ClipReport now carries event_identity="UNVERIFIED", and the summary line prints "mechanically admissible" plus an explicit UNVERIFIED notice. This is a truthfulness fix, not a threshold tweak.
  -> NOT DONE: the held-out protocol surf prescribed (independent positive labels, realistic negatives, frozen bounds, stated false-accept target, temporal/texture features, DC first). I did NOT re-fit profiles and will not, per its instruction.
- FIXED THIS PASS: SP-02 (inode-pin: stat before open, fstat after, refuse if dev/ino changed — the resolve/open race), SP-08 (verify_binding now rejects ok!=True and size/frame mismatch), IS-07 (absent digest printed "digest verified" = false integrity success; now "digest UNVERIFIED"), IS-08 (interrupt_sfx declared dependencies=[] while importing pydantic; now declared, uv run resolves), IS-09 (constant DC passed "sustained audible"; AC component measured, DC repro now fails), SV-12 (a FIFO hung the "bounded" reader; O_NONBLOCK + fstat refuses it).
  Evidence: DC clip -> FAIL "no signal variation: ac_rms=0.0"; real tone -> PASS; FIFO -> refused in <3s (no hang); ok=false receipt -> refused; real receipt -> ok=True 252480 frames; uv run rc=0.
- STILL OPEN from A: SP-06 (failure after linking the WAV can remove evidence and leave the WAV), IS-06 (manifest failure leaves an unrecorded clip and blocks retry), SV-05 (generator and verifier nonverbal policies still disagree), plus minors SP-09/10/11, IS-10/11, SV-07/11/13/14/15.
- NEXT: surf recommends B in parallel since it is independent. I agree — A stays in fix/re-review, B proceeds concurrently.

## PACKET A THIRD FIX PASS — the three remaining majors closed (2026-11-12)
- SP-06 (failure after linking the WAV strips evidence / leaves the WAV): cleanup now owns exactly the three names this attempt created and unlinks each INDEPENDENTLY (out, receipt, provenance) with per-path try/except, plus staged temps. A sidecar unlink failure can no longer abort the loop. PROVEN by injecting a failure at the WAV publish (3rd call): render raised, leftovers = none — no orphan WAV, no stripped evidence.
- IS-06 (manifest failure leaves an unrecorded clip and blocks retry): a _commit_manifest exception now unlinks the just-installed clip and reports MANIFEST COMMIT FAILED, so the filesystem and manifest stay in agreement and the retry is not blocked. PROVEN: injected OSError("disk full") -> rc=1, leftover clips = none, manifest entries = [].
- SV-05 (generator and verifier nonverbal policies disagreed): policy extracted to scripts/sfx_policy.py as the single source of truth (NONVERBAL_ALLOWED, classify_cue, MAX_CUE_WORDS). Both interrupt_sfx.py and sfx_verify.py import it, so a transcript cannot be accepted by one and rejected by the other. Retained selftest: 8 accepts + 5 rejects, PASS (it rejects "Please stop talking now.", "I will see you again tomorrow", "Yes.", and a repeated-token sentence).
- REGRESSION after all changes: 81/81 PASS and the report now prints "mechanically admissible" plus "event_identity: UNVERIFIED for every clip" (/tmp/verify-final.json).
- STILL OPEN (surf, packet A): minors SP-09 (CLI usage crash), SP-10 (trailing newline in message IDs), SP-11 (incomplete final frame), IS-10, IS-11, SV-07, SV-11, SV-13, SV-14, SV-15.
- NEW WORK ITEM, NOT A THRESHOLD TWEAK: event identity is UNVERIFIED by construction. Closing it requires the held-out protocol surf prescribed — independently adjudicated positive labels, realistic negatives (tones, beeps, DC, silence, spoken event names, ordinary sentences, other categories), a provenance split, bounds frozen against a stated false-accept target before the held-out test, and temporal/texture features per event. Do NOT re-fit profiles against the current library; that is what produced the in-sample 81/81.

## PACKET A MINORS CLOSED (2026-11-12) — third pass ready for review
Every minor from surf's second review is fixed, plus two new shared modules so the same defect class cannot reappear in one path only.
- NEW scripts/wav_guard.py: the single strict WAV reader both modules use. Validates real RIFF chunk extents (not wave.getnframes(), which floors a declared size to whole frames), rejects truncation, a partial final frame (321 declared / 320 present), non-PCM, non-16-bit, bad rate/channels, malformed fmt (EOFError/struct error becomes WavError), and reads via O_NONBLOCK so a FIFO cannot hang it. PROVEN: 321/320 rejected; FIFO refused without hanging; normal WAV ok.
- SP-09: usage path used len(argv) < 2 while requiring TEXT OUT -> TypeError with no args, IndexError with one. Now SystemExit(2) with usage.
- SP-10: _ID_RE.match + '$' accepted "test\n" as a message id, which then entered filenames/receipts. Now fullmatch.
- SP-11: payload check now validates declared data extents and frame alignment, not just complete frames read.
- IS-10: duration and peak gates now use RAW values (seconds_raw/peak_raw); a 2.004 s clip is no longer rounded into the 2.00 s maximum. PROVEN: 2.004 s -> FAIL, raw=2.0040.
- IS-11: gate()/measure() now decode through wav_guard, so an unsigned PCM8 silent WAV cannot measure as peak/rms ~0.9961. PROVEN: rejected "8-bit samples; PCM16 required". A real cue still passes (0.88 s).
- SV-11: a clip whose content gate did not run is now ACOUSTIC_ONLY, not PASS. PROVEN: --all --no-asr reports "0/81 PASS · 81 ACOUSTIC_ONLY (content not screened)".
- SV-13: a malformed fmt chunk fails that clip instead of aborting the batch.
- SV-14: incomplete final PCM frame rejected (shared guard).
- SV-15: manifest entries are typed (ManifestEntry: id charset, non-empty category/file, sha256 must be 64 lowercase hex when present). A present-but-empty digest now fails validation instead of silently disabling the comparison. PROVEN: empty sha256 -> "invalid manifest entry x1" reported as a FAIL row, rc=2.
- REGRESSION: 81/81 PASS with all gates completed; 0/81 PASS + 81 ACOUSTIC_ONLY with --no-asr (/tmp/verify-pass3.json, /tmp/verify-noasr.json). All five modules import; sfx_policy selftest PASS.
- PACKET A now awaits a THIRD surf review. B (arc/delivery) is independent and was offered in parallel.
- REMAINING WORK ITEM (not a threshold tweak): event identity stays UNVERIFIED until the held-out protocol is run — independent positive labels, realistic negatives, provenance split, bounds frozen against a stated false-accept target, temporal/texture features per event. Do not re-fit profiles to the library.

## INLINE TAG PROBE (2026-11-12) — the tag has NO reliable effect yet
Question from the operator: why can't LoRA teach Chatterbox to recognise tags like [sigh]?
Cheapest decisive probe first, before any consultation or training run.
- Run 1 (n=4 each, alex/neutral_warm, same sentence): plain 2.24 s (2.04-2.44) vs tagged "[sigh] ..." 2.59 s (2.40-2.72). Ranges did not overlap, which LOOKED like a real effect.
- Run 2 (same setup, n=1 each): plain 2.60 s, tagged 2.40 s. The sign REVERSED.
- ASR on both: "I need a moment before I answer that." on BOTH. The tag is not spoken aloud (no "sigh" word), and no lexical artifact appears.
=> The apparent duration effect in run 1 was sampling noise. With n=4 it can manufacture clean-looking separation - the same failure as the LoRA v9 "3/3 PASS". Current answer: the inline tag produces no reliable acoustic change in the current model. It is essentially inert, not "weakly learned".
- IMPLICATION: LoRA would be teaching a mapping that does not exist yet, from scratch, with ~tens of examples - which is why v9 gave ordering-with-noise rather than events. It is NOT proof that training cannot work; it is proof that my experiments did not have the power or the contrast to establish it.
- NOT YET DONE: a powered experiment (contrasted categories, seed sweep, effect size vs noise floor, frozen eval before training). That is the decisive test, and it must be designed before another training run.

## PACKET B REVIEW → FAIL (2026-11-12) — ALL FINDINGS FIXED, awaiting B pass-3 verdict
surf returned packet B FAIL (all four files). Majors:
- arc_chart AC-01: receipt text injected raw into SVG markup (injection); AC-02: output writes can destroy the input or an existing file.
- speak SK-01: session IDs escape the session dir (path traversal); SK-02: arc partitioning silently drops trailing sentences; SK-03: arc rendering silently discards rendering controls.
- speak_core SC-01: service-supplied WAV paths not confined to mapped host roots; SC-02: overlong tags disappear from the fail-closed gate; SC-03: per-chunk intensity bypasses the numeric/vocabulary boundary.
- test_core_contract TC-01: gain correctness neither exercised nor asserted; TC-02: digest asserts do not establish content/transport binding; TC-03: deep-snapshot protection claimed without a nested-mutation test. TC-05: under python -O the asserts vanish and PASS still prints.
- Minors: AC-03, SK-04, SK-05, SC-04, TC-04.
- surf deviation to note: its preflight refused the packet for containing real local paths, so it rewrote them to placeholders in ITS copy (my original untouched, no code bytes changed). It also flagged that my packet generator emitted "+++ /dev/null": root cause is that these files are UNTRACKED in this worktree, so `git diff origin/main -- <path>` renders them as deleted. My pass-3 packets are now full-content with zero absolute paths.
- STATUS CORRECTED 2026-11-12 (this line previously said "NOTHING from B is fixed yet", which would have sent a future agent to redo finished work): ALL Packet B findings are FIXED and were submitted to surf as B2 (pass 2) and B3 (pass 3). Evidence verified in code and by re-running the contract test now: AC-01 escape path present (arc_chart.py, 8 hits), SK-01 confined session path (speak.py, 4 hits), SC-01 confinement + SC-02 overlong-tag gate (speak_core.py, 5 and 2 hits), TC-01 gain-bound assertions (test_core_contract.py, 9 hits), and `python3 test_core_contract.py` -> rc=0 PASS_CORE_IMPORT_CONTRACT.
- What actually remains for B is a VERDICT, not work: awaiting surf's B pass 3 (B2 superseded by B3 per their queue). That is tracked in the blocked list, not here.

## QUEUED — powered tag-effect experiment (before ANY further LoRA work)
103. [x] Decide whether inline emotion tags carry a learnable signal. ISOLATED, /tmp only, no production code. DONE 2026-11-12.
    RESULT: SIGNAL_EXISTS_BUT_UNDIFFERENTIATED. Inline tags are NOT inert - my earlier "inert" reading (n=1/n=4, sign reversed between runs) was sampling noise and is RETRACTED.
    Evidence: receipt /mnt/storage12tb/skills/chatterbox-speak/outputs/tag-signal-probe-20261112.json (sha256 78aca6db8a26156b), raw cells /tmp/tagfx/cells.json.
    Setup: 4 tags x 2 sentences x n=10, alex/neutral_warm, plain baseline per sentence.
    - Every tag lengthens the render beyond the noise floor: Cohen's d 1.09-5.78, replicating in BOTH independent halves, 7/8 cells with non-overlapping bootstrap CIs.
    - But tags barely separate from EACH OTHER: max d=1.67 ([laugh] vs [gasp], s0) and 1.34 ([laugh] vs [sigh], s1).
    - ASR never transcribed the tag word; it DID transcribe inserted vocalisations for groan ("Ugh","Uh") and gasp ("Ah","Oh"), never for sigh/laugh.
    => The model currently treats a tag as "insert some nonverbal audio here", not "produce THIS event". What training must learn is DISCRIMINATION, not existence.
    => Feasibility for the operator's goal ("add tags to the text and have chatterbox respect them") is therefore POSITIVE in principle.
104. [~] PAUSED by owner: teach tag->event DISCRIMINATION (successor to the tokenizer probe).
     PAUSED awaiting Graham: the GPU run was stood down by him on 2026-11-12 (researcher seq 11: "I run the MVPs so your context stays clean of experiments"); see item 108 for that decision.
     Why it exists: LoRA vocalisation was measured at the ceiling (2/3 gates, EL-sigh DROP 2/8 seeds), and the S3 codec probe showed reference-dependence (neutral-reference log-mel .655-.767 for SFX vs .927/.941 for speech). Discrimination — telling a laugh from a cough from a sigh in generated tokens — is the surviving route, and it needs a GPU window the owner controls.
     Do NOT start it in the researcher lane without his go: the codec discovery MVP (item 98) is the current owner-approved experiment.
     OWNER: Graham (GPU window / go-ahead), then researcher (run).

11. [~] Ear verdict on the 59 verified clips at http://127.0.0.1:8797/ — blocked awaiting Graham. Say "confirm all", "confirm [ids]", "reject [ids]", or "regenerate [category] with [change]". Nothing else in the SFX track can advance until the manifest carries real verdicts.
     REVIEW SURFACE REPAIRED AND VERIFIED LIVE (2026-11-13):
     - The `:8797` server was a STALE PROCESS from **Nov 10** (PID 2238598) that predated the current
       `scripts/listen_review.py` (`e178ee7621f0…`), so it 404'd `/api/clips` — the endpoint the
       reviewer needs to enumerate clips. Lesson applied: check WHICH ARTIFACT IS EXECUTING, not just
       that the code on disk has the route.
     - Restarted on current code (PID 1852593, Nov 12 20:29). `curl :8797/` -> 200 ("SFX Listening Review"),
       `curl :8797/api/clips` -> **200, 58,828 B, 74 pending clips**, keys include `asr_transcript,
       category, duration, event_identity, exists, file, frames, id`.
     - Category counts served: chuckle 10, gasp 11, groan 10, laugh 9, crying 9, cough 6, sniff 6,
       surprised 6, clear-throat 2, delaying 2, sighing 2, tissue 1 — **matches the 74-clip frozen eval**
       (`eval-freeze-v1.json` `876542cfc437…`) exactly, so the surface and the freeze agree.
     - `:8801` (steering ear test) also 200; `:8018` (chatterbox), `:8799` (render) listening.
     REMAINING BLOCKER IS THE OWNER'S EAR, not the tooling: 52+ of 74 clips still need a verdict; only
     `sigh-weary` and `sigh-shaky` are confirmed. A machine PASS never substitutes for that listening.

## NEXT UP (open)
105. [x] Surf Packet B pass 3 FAIL — 19/19 findings FIXED and PROVEN (report /tmp/surf-cb-B3/response.md sha256 fd044e6f2ea72674).
     Evidence: /tmp/pb3-proof/receipt.json 13/13 `db3f8a4c6e6e6c36` (AC-02, SK-01, SC-01, AC-04 — forced race, byte hashes); receipt2.json 7/7 `151e5bd15d0cdd41` (SC-05 exact-body digest, SC-06/SC-08 delivery merge, SC-09 WAV validation, SK-08 unique run dirs); receipt3.json 10/10 `662d4c8f5e03de38` (SC-04 receipt fields from the snapshot, SK-09 final-text laugh gate, SK-10 chunk transcript, AC-05 escaping); receipt4.json 19/19 `708b715b5db969ff` (SK-06 sentence preservation 5/9/10/13, SK-07 option forwarding + mode refusal, SC-07 gain on the wire, SC-10 revalidation, SC-11 owned `audio.wav`); `test_core_contract.py` rc=0 with the TC-02 body-digest oracle, TC-04 valid fixtures/only UnsupportedTagError, TC-06 non-silence + measured gain.
     Retained eval: `../agentic-evals/run.sh run fixtures/agentic_eval.json --timeout-seconds 900` → READY, PASS 13 / FAIL 0, 135,298 B sha `f7373ca244380a4e7`.
     Owned defect: cb-B3a shipped one real local path (`/mnt/storage12tb/skills/chatterbox-speak/outputs`); the sanitizer must cover the outputs root, not just the library path.
     Two self-caught errors from the proofs: the SC-09 duration fix first missed the 24-space return (proof showed 999.0), and SK-07's forwarding referenced `ref`, which is bound only on the non-arc path (UnboundLocalError). Both fixed and re-proven.

106. [x] FOLDED INTO 102 — this packet is tracked as one of the three waiting behind the single surf transport outage.
107. [x] A7 pass 17: SP-30 PARTIAL and IS-28 PARTIAL closed by REMOVING the name race; packet DELEGATED.
     PRODUCTION (current bytes): `fs_ops.py` `8c8e70c0…` — `stage_bytes` stages with `O_TMPFILE` (no name to swap) and falls back to a named temp only where unsupported, still publishing from the descriptor; `link_fd_no_clobber` links `/proc/self/fd/N` with `AT_SYMLINK_FOLLOW` and verifies the installed inode against the descriptor's; `replace_from_fd` materialises inside a private 0700 `mkdtemp` directory (no writer can rename into it) and verifies the replaced inode. `spyke_render.py` `7360be49…` — `_publish` takes the DESCRIPTOR, refuses a stale inode claim (`fstat(fd)` must equal the claim), closes descriptors on both paths, and never unlinks a staging name. `interrupt_sfx.py` `6fac56c9…` — `_commit_manifest` stages privately via `stage_bytes` and verifies before reporting a commit.
     PROOFS `tests/test_a7_pass10_repairs.py` **49/49** with caught mutants: SP-30 stale claim (production refuses, mutant publishes), SP-28 fallback failure (production parks, mutant unlinks), IS-28 replace-that-installs-nothing (production raises, mutant claims a commit); `test_prove8.py` **34/34**; `test_packet_a7_reporting.py` 30/30; `test_t1_pass10_repairs.py` 24/24.
     GATES: `tests/run.sh` **rc=0**, all retained harnesses PASS; `./sanity.sh` **rc=0** with a live render.
     PACKET `/tmp/cb-A7-pass17.txt` **209,233 B** sha256 `0c26575954ccdeeda2996781edeef2279710d10e2e6da9f2a7d82f02a8bd8cb8`, **9/9 bindings re-hashed, drifted none**, DELEGATED to surf.
     RECORDS: 5 rows re-pointed (fs_ops, spyke_render, interrupt_sfx, test_prove8, test_a7_pass10_repairs); matrix A7 = `PASS`(2) + `cb-A7-pass17`(7); plan pinned; delegations updated. THIRD MISSING-ROW INSTANCE this session: `scripts/fs_ops.py`, `tests/test_a7_pass9_repairs.py` and `tests/mutant_support.py` had NO manifest rows — all three added before delegation so verdicts can be first-class.
     DOC **LANDED `7bf64495ac10…`**; checker names pass 17; identities re-recorded deliberately (`a1a20adb…`).
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`); packet bindings verified after the record work.
     Verification: `python3 tests/test_a7_pass10_repairs.py` → 49/49; `bash tests/run.sh` → rc=0; `./sanity.sh` → rc=0; binding re-hash → 9/9, drifted none.

108. [x] FOLDED INTO 102 — this packet is tracked as one of the three waiting behind the single surf transport outage.
109. [x] Retain the proof harnesses IN-REPO — DONE and RUN from the repo.
     `skills/chatterbox-speak/tests/`: `test_packet_a7_reporting.py` (9,907 B sha `ef8017e75c18dd2a…`), `test_prove4.py` (6,111 B `fd10d037ae20ad63…`), `test_prove5.py` (4,232 B `4b1e01ab1b1503c6…`), `test_prove6.py` (3,877 B `3be999c90f3ca402…`), `test_prove7.py` (6,552 B `619999c0d63a6da0…`).
     Every `/home/graham/...` and `/tmp/pb3-proof|pa7-proof` reference removed (verified by grep): scripts resolve via `Path(__file__).resolve().parents[1] / "scripts"`, receipts are written under `tests/receipts/`.
     Run from the repo, all rc=0: 22/22 (packet A pass 6), 13/13 (AC-02/SK-01/SC-01/AC-04), 7/7 (SC-05/06/08/09, SK-08), 10/10 (SC-04, SK-09/10, AC-05), 19/19 (SK-06/07, SC-07/10/11). Receipts in-repo: `tests/receipts/packet_a7_reporting.json` + `packet_b_prove4..7.json`.
     `./sanity.sh` rc=0 (live render OK) after the changes. These are new `.py` files, so they do not land until surf passes them and `$gh-land` is given explicit paths.

110. [x] Landing prep DONE — blob-vs-file audit; manifest written, nothing landable yet.
     Manifest: `/mnt/storage12tb/skills/chatterbox-speak/outputs/landing-manifest-20261112.json`, 17,971 B, sha256 `9f8e88db8fc7630d29628a7652e00bdea1b1b6ebf4fd8da1d42ccdce72a7363d` (`chatterbox.landing_manifest.v1`).
     Method: for each of 21 files, `git show origin/main:<path>` compared with the local bytes (NOT `git diff`, which misreports untracked paths). 12 files exist on origin/main; 9 are new there. Every file carries the full 64-char local sha256, origin/main blob sha (or null), and +/− line counts.
     Removals: 89 origin/main lines removed across 4 files — speak_core 33, speak 39, arc_chart 16, test_core_contract 1. Every removed line is captured verbatim in the manifest with a per-file verdict; each maps to a finding fixed this session (SC-01/04/05/06/07/08/09/10/11, SK-01/06/07/08/09, AC-02/05, TC-02). No unexplained removal.
     Coverage recorded per file: `sfx_policy.py` PASS (A pass 6), `wav_guard.py` PASS (excluded as already passing); PENDING — B4 (speak_core, speak, arc_chart, test_core_contract), A7 (sfx_verify, spyke_render, interrupt_sfx), render_service, LP, EL trio; NO RECEIPT — `narrator_sfx_batch.py`; NOT REVIEWED — the 5 new `tests/*.py`. `landable_now` is false for all 21 by design.

111. [x] Tests + orphan packet (T1b) — LANDED, so the old "verdict pending" state is obsolete.
     Commit `7d290c89aafa…` landed `tests/test_t1_pass10_repairs.py` (`7ed5445d…`) and `tests/run.sh` (`11fc4e3f…`) under a JSON reviewer receipt (`5ef9cf3b…`, greenfield).
     Commit `747f2e881d0e…` landed `tests/.gitignore` (`cc8d40de…`) and `sanity.sh` (`d19f6382…`).
     Origin blobs re-read after each push and equal local bytes; `landing-check.sh T1` and `T1b` both CHECK PASS; board eleven guards PASS.
     No work remains under this item (the T1b packet that once covered it is superseded by T1 pass 17, item 97).

112. [x] Gate the retained harnesses — DONE with a mutation control.
     `skills/chatterbox-speak/tests/run.sh` (executable) runs all five harnesses, prints per-test PASS with its count, and `exit 1` if any fails; `tests/.gitignore` excludes the regenerated `receipts/` so the tree stays clean.
     Gate run: rc=0 — 22/22, 13/13, 7/7, 10/10, 19/19, "all retained harnesses PASS".
     Mutation control (the gate must not be decorative): injected one failing check into `test_prove5.py` → gate rc=1, `FAIL test_prove5.py rc=1`, other four still PASS, "FAILURES present". Restored from a byte-exact backup: sha256 back to `4b1e01ab1b1503c643c0c887ba4e969b9908bf2506153f4ff54a98f98089486d`, gate rc=0 again.
     This makes the A6/B3 evidence continuously checkable instead of a one-off /tmp artifact.

113. [x] `sanity.sh` now proves the retained harnesses — with a mutation control that caught my own first wiring.
     `sanity.sh` sha256 `d5d9e2a4…` (read back below), calls `./tests/run.sh` between the static self-checks and the negative control, emitting "retained harnesses OK".
     Gate run: `./sanity.sh` rc=0, log contains "tests: all retained harnesses PASS" + "retained harnesses OK".
     Mutation control 1 (the defect): the first wiring was `./tests/run.sh && echo ...`. Under `set -e`, a failing command that is NOT the last in an `&&` list does NOT abort, so the mutated run returned rc=0 while printing "tests: FAILURES present" — a decorative gate. Fixed to `if ! ./tests/run.sh; then echo "FAIL: retained harnesses regressed"; exit 1; fi`.
     Mutation control 2 (after the fix): injected one failing check into `test_prove6.py` → `./sanity.sh` rc=1 with "FAIL test_prove6.py rc=1", "tests: FAILURES present", "FAIL: retained harnesses regressed". Restored byte-exactly (sha256 back to `3be999c90f3ca402…`); `./sanity.sh` rc=0 again.

114. [x] Landing manifest refreshed with the three paths — DONE.
     `/mnt/storage12tb/skills/chatterbox-speak/outputs/landing-manifest-20261112.json` now 20,158 B, sha256 `5f2a3911c0ec0e6e3d7b7295bec27ac114f0b66580dc839d1c98249972089821`, 24 files.
     Read-back verified: every row carries a 64-char sha256 (`bad_sha=[]`), every row has a named reviewer (`missing_review=[]`), `landable_now=true` count is 0, and 22 paths are listed as blocking.
     Added rows (all with origin/main state, +/− counts, and coverage):
     - `tests/run.sh` — absent on origin/main, +19, sha256 `9701df1f…`, NOT REVIEWED (shell; outside the `.py` requirement, listed for completeness)
     - `tests/.gitignore` — absent, +2, sha256 `cc8d40de…`, NOT REQUIRED (excludes regenerated `receipts/`)
     - `sanity.sh` — origin `cb6ac61c…`, +11/−0, sha256 `7f64a078…`, NOT REVIEWED (shell; fail-closed harness gate added)
     The manifest note now records that `.sh` is outside the cross-provider reviewer requirement for `.py/.ts/.js/.mjs/.cjs` while still belonging to the skill's evidence surface.

115. [x] Documentation drift from publish-once — WRITTEN and LANDED (`6981fe3fe2`).
     New `references/verification-evidence.md` (5,192 B, sha256 `5debfa8c794805d9…`) documents: never verify against the live manifest (copies it first, records the 2026-11-12 truncation), the publish-once `--out` contract with the exact refusal message, what PASS/ACOUSTIC_ONLY actually prove, ASR-as-advisory, policy-unavailable = failed gate, acoustic profiles as plausibility filters, the retained `tests/run.sh` gate with its five counts, and `interrupt_sfx.py --selftest`. Linked from SKILL.md's References section.
     Behaviour was captured live before writing, not assumed: first run rc=0 (46,718-byte report), second run to the same `--out` rc=2 with "--out … already exists; refusing to overwrite an existing file (a report is publish-once evidence …)"; `tests/run.sh` rc=0 (22/22, 13/13, 7/7, 10/10, 19/19); `interrupt_sfx.py --selftest` rc=0.
     Drift sweep result: 0 doc lines combine `sfx_verify` with `--out` (grep), so no example taught the refused pattern. The one fixed `--output` in SKILL.md:280 is an `agentic-evals` artifact (`contextual-report.json`), not a publish-once report; every publish-once example in the new doc uses `mktemp -d` or a per-run name.
     Landing verified: `git show origin/main:<each path>` hashes equal the local files (SKILL.md `d26f40ce…`, verification-evidence.md `5debfa8c…`). Docs need no reviewer receipt.

116. [x] Landing manifest reconciled with reality — DONE.
     `/mnt/storage12tb/skills/chatterbox-speak/outputs/landing-manifest-20261112.json` now 22,632 B, sha256 `e0a1f26993f703675820209da0c60b81370b89cf87130215fb6953f34c9bca84`, 26 rows (24 code/test paths + 2 docs).
     Blob-vs-file comparison re-run for EVERY row; `bad_sha=[]` (every sha256 is 64 chars), `landable_now=true` count is 0, blocking list is 22 (landed docs excluded).
     The two landed docs are recorded with `status: LANDED 6981fe3fe2` and their origin/main blobs equal the local files: `SKILL.md` `d26f40ce8897…` == origin, `references/verification-evidence.md` `5debfa8c7948…` == origin. A `status` field now distinguishes LANDED docs from "BLOCKED pending reviewer verdict" code paths.

12. [x] Doc drift fixed via option (a) — AMENDED and LANDED (`35057c53d8`).
     `references/verification-evidence.md` now opens the Retained evidence gate with a status block: the harnesses live in the working tree and are **not yet on `origin/main`** (waiting on Packet T1 review), so the counts and mutation control are explicitly attributed to the working tree. Every other statement in the doc was already true of main.
     Landed-bytes check: local sha256 `a2a1e7b978165d3f7ff64ef8985433f6a0b4b40c4d6d70f6691830915b99d18a` == `git show origin/main:...` (LANDED MATCH: YES). The note is present on main (line 64).
     Truth check of the note: `git cat-file -e origin/main:.../tests/run.sh` still FAILS → "not yet on origin/main" is accurate, not a hedge. Option (b) — landing `tests/` — remains open until T1 passes; the doc no longer implies otherwise.

13. [x] Manifest row for `references/verification-evidence.md` refreshed — DONE.
     Row sha256 `5debfa8c7948…` → `a2a1e7b97816…`, `status: LANDED 35057c53d8`, `landable_now=false`, `added/removed = 0/0` with the verdict "origin/main now carries these exact bytes".
     Read-back of the rebuilt manifest: 22,633 B sha256 `4c72afa902ee891fa0cba7b5af53f0ac08fef9afd8ac57797715644905060aab`; 26 rows; local==origin for the row (True); blocking list unchanged at 22; `landable_now=true` count 0; `bad_sha=[]`.
     Nothing else moved: the 22 blocked code/test paths still wait on A7/B4/T1.

14. [x] Landing plan prepared (nothing landed) — DONE and self-checked.
     Artifacts: `outputs/landing-plan-20261112.md` (6,461 B sha256 `e3685c21f6afc739…`), `outputs/landing-plan-20261112.json` (4,796 B sha256 `7e6e8c21408ebb82…`), `outputs/landing-check.sh` (sha256 `900ff89f02088eca…`).
     Seven groups, each one exact `$gh-land` command with explicit paths: B4 (speak_core, speak, arc_chart, test_core_contract), A7 (sfx_verify, spyke_render, interrupt_sfx), T1 (5 tests + narrator_sfx_batch), T1b (tests/run.sh, tests/.gitignore, sanity.sh — needs packet inclusion first), EL (4 ops-elevenlabs modules), render_service, LP. 22 paths total; every row carries the full 64-char local sha256 alongside the origin/main blob sha or ABSENT.
     Pre-land check: `landing-check.sh <GROUP>` verifies the local hash still matches the plan and that origin/main has not moved (or a "new" file has not appeared on main). All seven groups returned `CHECK PASS`, overall rc=0.
     Two self-caught defects in the check itself, both fixed before claiming it works: (1) the repo root was derived as `../../..` from the data volume, so every path reported MISSING; (2) `SCRIPT_DIR` was computed after `cd "$ROOT"`, so the plan was looked for inside the repo. It now pins its own directory first and validates `git rev-parse --show-toplevel` before reading anything.

15. [x] SUPERSEDED, not pending: the T1b addendum packet (`/tmp/cb-T1b.txt` `2b9aba9a…`) bound `tests/run.sh` `9701df1f…`, but the live file is `11fc4e3f…` (T1-39 added the per-harness `timeout 180`). Its three files — `tests/run.sh`, `tests/.gitignore` (`cc8d40de…`, unchanged), `sanity.sh` (`d19f6382…`, unchanged) — are ALL carried by the current T1 pass-17 packet (`2b81ad98…`), which includes `run.sh` and `sanity.sh` with live hashes. Applying a verdict from the old packet would bind a verdict to bytes that moved, so it is retired here, not processed.
     Evidence: `sha256sum tests/run.sh` = `11fc4e3f…`; the T1 pass-17 binding list contains that hash. No work remains under this item.

16. [x] EL landing-completeness audit — the 4 modules could not land as a working skill unless the support files were already on main; they are.
     Verified per file (local sha vs `git show origin/main:`): `SKILL.md`, `pyproject.toml`, `references/api-surface.md`, `run.sh`, `scripts/sanity.sh` are all IDENTICAL to origin/main, so no action. Only the 4 `src/ops_elevenlabs/*.py` modules are absent.
     The gap found: `skills/ops-elevenlabs/uv.lock` was missing from the plan. 111 skills track `uv.lock` on origin/main, and this one is not gitignored, so it belongs in the EL group. Added to the manifest (27 rows now, 23,242 B sha256 `6a93ba540b0cf7d2…`, blocking 23) and to the landing plan's EL group (now 5 paths); `landing-check.sh EL` → CHECK PASS.
     `uv.lock` row: sha256 recorded, origin/main ABSENT, review "lockfile (not code; included in EL packet for completeness)", `landable_now=false`.

17. [x] Landing plan MD/JSON consistency — VERIFIED, with a self-caught false positive.
     Checker persisted at `outputs/landing-plan-consistency.py`; receipt `outputs/landing-plan-consistency.json` sha256 `7779dfe058f40f8e0d39cf8607669bc45debb33200d316c8f772a4ef34941b90`, verdict CONSISTENT, rc=0.
     For all 7 groups it asserts three things: the MD table's path set equals the JSON group, the paths inside that group's `gh-land` command equal the JSON group, and every path exists on disk. Result: `groups checked=7/7 problems=0`.
     First run reported 2 problems attributed to T1: my matcher used `title.startswith(label)`, so the **T1b** section matched the **T1** key and its three shell paths (run.sh, .gitignore, sanity.sh) were scored against T1's six. Fixed to exact label equality; re-run is clean. The plan itself was never inconsistent — the checker was.
     This guards the hand edits: the uv.lock table row and command path were appended by index slicing, which is exactly where markdown/JSON drift hides.

18. [x] Plan vs manifest hashes AGREE — verified, receipt persisted.
     Checker `outputs/landing-plan-vs-manifest.py`; receipt `outputs/landing-plan-vs-manifest.json` sha256 `364fd4a281640e62a2103e4fd544413d52f04fbd95fd03ba80a151c8bbef108e`; rc=0.
     Checked 23 planned paths against 27 manifest rows: per-path sha256 equality, origin/main equality, the LIVE file still hashing to the plan's value (catches a stale plan), no plan path absent from the manifest, and no landed path still sitting in the plan. Result: `plan paths checked=23 manifest files=27 planned=23 landed=2`, 0 problems, VERDICT `AGREE`.
     The two landed docs are correctly excluded from the plan (planned ∩ landed = ∅), and `uv.lock` (added by hand to the plan) is present in both with identical hashes.

19. [x] Both consistency checkers mutation-controlled — each FAILS on injected drift and passes again after restore.
     Ran on throwaway COPIES (`/tmp/mut-check1`, `/tmp/mut-check2`), never the real plan files.
     A. `landing-plan-vs-manifest.py`: set `speak_core.py`'s plan sha to 64 zeros → VERDICT `DRIFT`, rc=1, two independent catches ("sha drift plan=000000000000 manifest=2d44ee89ffe4" and "changed since the plan (2d44ee89ffe4 != 000000000000)"). Restored copy → `AGREE`, rc=0.
     B. `landing-plan-consistency.py`: injected a stray MD table row `skills/chatterbox-speak/scripts/NOT_REAL.py` → VERDICT `INCONSISTENT`, rc=1 ("md table 5 != json 4 only_md=[...NOT_REAL.py]"). Restored copy → `CONSISTENT`, rc=0.
     Originals byte-exact and untouched: plan JSON sha256 `24a32e79ab18daa7…`, plan MD sha256 `79c2486c995f1754…` both verified after the runs; the real receipts still read `364fd4a2…` (AGREE) and `7779dfe0…` (CONSISTENT). The mutation runs wrote their receipts inside the temp copies only.

20. [x] Landing-safety gap CLOSED — `landing-check.sh` now gates on the reviewer verdict, not just hashes and origin state.
     New third gate: every path in the group must carry `review_verdict` PASS/LANDED in the manifest. Exit codes are distinct — 0 pass, 1 hash/origin mismatch, 2 usage/setup, 3 review-blocked. `--force-unreviewed` is the explicit opt-out for shell/docs groups, and it still runs gates 1–2.
     Mutation control, all four directions (real plan/manifest untouched, verified by sha afterwards: plan `24a32e79ab18daa7…`, manifest `6a93ba540b0cf7d2…`):
     - real B4 (4 PENDING) → rc=3, each file named `REVIEW PENDING … -> PENDING`, "CHECK REFUSED … 4 file(s) have no PASS verdict"
     - real B4 with `--force-unreviewed` → rc=0 `CHECK PASS`, after printing "forced past 4 unapproved file(s)"
     - real T1b (NOT REVIEWED / NOT REQUIRED) → rc=3, 3 files refused
     - temp copies: all 4 B4 rows marked PASS → rc=0 `CHECK PASS`, no force needed; then ONE row (`speak.py`) set back to PENDING → rc=3 naming only that file (per-file granularity, not group-level theatre)
     The `--force-unreviewed` path is proven non-destructive to gates 1–2: a hash mismatch would still exit 1 in the same invocation.
     Script sha256 recorded below; this closes the hole where a hash-clean but unreviewed group could have been landed by following the plan literally.

21. [x] Audited the researcher's EL-sigh LoRA MVP receipt (seq 14) — DROP CONFIRMED, with two corrections to the summary.
     Artifacts read (not just the prose): `/tmp/wsp-mvp/lora/evaluation.json` (10,124 B), `FROZEN_REFERENCE.json` (1,503 B), `adapter.pt` (18,904,182 B), 16 eval WAVs. Recomputed every headline number myself from the rows.
     Confirmed against the frozen bar: `required=6`, `passed=2` (seeds 4 and 6), verdict `DROP`. LoRA speaker similarity 0.875–0.915 (bar ≥0.80), LoRA recall 1.0 on every seed (base min 0.833), seed 5 ASR extras `['hmm','hmm']`, frozen slot floor 0.41 s, centroid band 1494.4–2490.6 Hz.
     Correction 1: ".04 s -> .40 s" are SLOT-AUDIBLE medians, not duration medians. Actual duration medians are base 3.32 s -> LoRA 4.72 s. Both matter, but conflating them overstates the duration claim.
     Correction 2 (near-miss structure, absent from the summary): 6/8 LoRA seeds sit inside the centroid band (0,1,2,3,4,6) and only 3/8 clear the slot floor (4,5,6). Seeds 0,1,2,7 miss ONLY the slot, by 0.01–0.11 s (0.40/0.38/0.30/0.40). That is partial learning, not a null result.
     Recall caveat checked: `recall_floor=0.9` = base median (1.0) − 0.1, so it is not "literal unchanged"; but all LoRA seeds scored 1.0, so the verdict does not depend on it. Their caveat was accurate.
     Claim boundary recorded: DROP means "does not transfer reliably at this scale (150 pairs, 500 updates, ONE held-out sentence, no ear acceptance)", NOT "EL targets cannot transfer at all". Production stays on the approved SFX clips. The frozen bar's DROP wording should be narrowed accordingly before any future run quotes it.

22. [x] Preserved the MV4 LoRA evidence out of `/tmp` and recorded the narrowed DROP claim — DONE.
     `/mnt/storage12tb/skills/chatterbox-speak/outputs/el-sigh-lora-mvp4-20261112/` now holds 23 files (`evaluation.json`, `FROZEN_REFERENCE.json`, `mvp4.py`, `score.py`, `slot.py`, `raw_result.json`, 16 WAVs) with per-file sha256 in the receipt. `AUDIT.json` 5,109 B sha256 `5cc0943cd63f9c785d48b31cfb25aadb30ecd698e8580a89ee4c476316b4d11b`.
     The receipt records: verdict DROP at 2/6 required; base vs LoRA slot-audible medians 0.04 vs 0.40 s; duration medians 3.32 vs 4.72 s; LoRA centroid 6/8 in band; sim 0.875–0.915; LoRA recall 1.0; the two corrections to the summary (slot vs duration; the 4 near-miss seeds); the recall-floor caveat; and the claim boundary.
     Claim boundary now explicit: DROP means the target does not transfer RELIABLY at this scale (150 pairs / 500 updates / one held-out sentence / one voice / no ear acceptance); it does NOT establish that EL targets cannot transfer at all. Production stays on the approved SFX clips.

23. [x] Closed paths recorded in the skill's own notes — LANDED `06944695dfea905cd2f81ea337a4fe4e6fb340c5`.
     `skills/chatterbox-speak/PARKED.md` now opens with "CLOSED BY MEASUREMENT (2026-11-12) — do not restart without new evidence", covering both rungs with their receipts and claim boundaries:
     - sigh steering (rank #2): probe receipt `outputs/sigh-steering-probe-chatterbox-20261112.json`; alpha NOT separable from the tagged baseline (0.14 vs 0.11 s, d=+0.39, p=0.4113), tag IS separable (0.14 vs 0.07 s, d=+2.14, p=0.0056), no arm reached the 0.35 s half-sigh bar (best sample 0.26 s); the MVP2 follow-up sweep (0.5/0.8 over layers 10/12/14) gave L12 α0.5 0.05 s and α0.8 0.00 s against a 0.04 s baseline, and L14 α0.8 broke speech (recall 0.698, slot found 2/8). Reopening requires a different site/vector/timing, not a re-tune.
     - EL-sigh LoRA (rank #1 family, one subtype): preserved audit `outputs/el-sigh-lora-mvp4-20261112/` (23 files, 16 WAVs, `AUDIT.json` sha256 `5cc0943cd63f9c78…`); DROP at 2/6 on the frozen bar; slot median 0.04 -> 0.40 s, duration 3.32 -> 4.72 s, 6/8 in the centroid band, sim 0.875–0.915, recall 1.0; four seeds missed only the slot floor by 0.01–0.11 s. Claim boundary stated as "does not transfer RELIABLY at this scale", explicitly NOT "cannot transfer at all"; reopening needs more held-out sentences, more data/updates, and ear acceptance.
     Both sections carry a dated `Status 2026-11-12` line so a reader who jumps straight to the idea sees the verdict.
     `GOAL.md` deliberately NOT modified: it is the immutable-goal contract and versioning rules require owner authorization for changes; the closure record belongs in PARKED.md, where the experiments live. Verified on origin: local sha `50b78ce1f44ce2fb4ae326b79b9ab5dba277ae38d532ca264a4a5b7d7cd7c1b8` == `git show origin/main:…/PARKED.md`; closure heading at line 10, both status lines present, both receipt paths present.
     One self-caught error: my first draft claimed "every alpha >=0.5 was quieter than 0.3", which the MVP2 artifact does not contain (it swept 0.5/0.8 only, and L12 alpha 0.5 measured 0.05 s). Corrected against `/tmp/wsp-mvp/mvp2/validation_report.json` before landing.

24. [x] Landing manifest reconciled with the landed notes — 0 bad hashes, blocking unchanged.
     Added `skills/chatterbox-speak/PARKED.md` as a LANDED row: sha256 `50b78ce1f44ce2fb4ae326b79b9ab5dba277ae38d532ca264a4a5b7d7cd7c1b8`, status `LANDED 06944695df`, `landable_now=false`, 0 added / 0 removed (this landing only added the closure record).
     Manifest now 23,909 B sha256 `3841d83dad1e1e0c…`: **28 rows, 3 landed, blocking 23 (unchanged)**. Integrity sweep over every row: landed rows verified against BOTH the live file and `git show origin/main:`; blocking rows verified against the live file — `bad_sha=[]`.
     All seven groups re-checked with the new verdict guard: unforced every group refuses (B4 4 files, A7 3, T1 6, T1b 3, EL 5, LP 1, render_service 1 — all rc=3), and the two shell/config opt-out paths still pass the hash/origin gates (`T1b` rc=0, `EL` rc=0 with `--force-unreviewed`). No group became landable by accident.

25. [x] Packet evidence archived out of `/tmp` — 5 files, every hash matches the one recorded in this queue.
     Destination `outputs/packets-20261112/` with `MANIFEST.json` 1,775 B sha256 `6da5a7649e54131e1c6987600068c4449dddc9d6fb38820a707559b172b6f499`, verdict `ARCHIVED_CLEAN`, `mismatches=[]`.
     Per file (actual sha256 == the value NEXT.md records, and each copy re-hashed byte-identical after copy):
     - `cb-B4a.txt` 103,469 B `09b0e2207d410dc9…`
     - `cb-B4b.txt` 56,813 B `18dcd308e9663497…`
     - `cb-A7.txt` 107,850 B `e8f3460393367e47…`
     - `cb-T1.txt` 52,461 B `9b06f192ce4105dd…`
     - `cb-T1b.txt` 5,453 B `2b9aba9a5034deb1…`
     Two extraction attempts before this cross-attributed hashes (`cb-B4b` picked up `cb-B4a`'s value; `cb-T1` picked up `cb-T1b`'s) because overlapping text windows captured the neighbouring filename's hash. Fixed by segmenting the queue text at each filename mention and taking only the first hash inside that segment; the item's "report any mismatch" rule is what surfaced it instead of archiving on a sloppy match.

26. [x] Packet→group coverage map BUILT — and it found four real gaps, not a clean board.
     Receipt `outputs/packet-group-coverage.json` 13,755 B sha256 `31987a95747df59c20b433c4e4f97fa7c7b920962870052859a1f887d930c3ab`, schema `chatterbox.packet_group_coverage.v3`.
     Method (v1 and v2 were wrong first): v1 counted any mention and cross-attributed hashes across neighbouring filenames; v2 required the full repo-relative path, but packets cite basenames. v3 binds by **current sha256 appearing in a packet of the file's own group**, and classifies everything else by what the packet actually binds.
     Against 25 blocking paths (23 planned + 2 unplanned) and 8 packet files on disk:
     - **REVIEWED 15** — B4 (speak_core, speak, arc_chart, test_core_contract), A7 (sfx_verify, spyke_render), T1 (narrator_sfx_batch + 5 tests), T1b (sanity.sh, run.sh, .gitignore).
     - **STALE_HASH 1** — `scripts/interrupt_sfx.py`: cb-A7 binds `0f85cb09e5a0…`, current file is `02061b290575…`. The A7 packet reviewed an older artifact; a PASS on it must not be read as covering the current file.
     - **UNBOUND_MENTION 5** — `scripts/lora_pipeline.py`, `scripts/render_service.py`, and EL `cli.py`/`client.py`/`models.py`: named in their packets but no hash bound in a ±400-char window, so coverage is asserted by prose only.
     - **UNPLANNED 2** — `scripts/sfx_policy.py`, `scripts/wav_guard.py` are blocking manifest rows sitting in NO landing group, so following the plan would never land them.
     - **UNCLAIMED 2** — EL `__init__.py` and `uv.lock` (the lockfile was added to the plan after its packet was submitted).
     The double-claim I reported mid-way (`test_prove6.py` in T1 and T1b) resolved correctly: T1 binds its hash; T1b mentions it only as the mutation-control target, not as reviewed scope.
     Consequence: no group is landable on a single PASS today; the plan's 7-groups-1-command-each shape needs the fixes in item 27 first.

27. [x] Coverage gaps CLOSED — all four subparts done, one correction delegated.
     (a) STALE HASH: `cb-A7.txt` binds `0f85cb09e5a0…` for `scripts/interrupt_sfx.py`; the file on disk is `02061b290575…` (583 lines, changed after A7 was assembled: IS-18 `_safe_synth` + `--selftest` refactor). Built `/tmp/cb-A7-interrupt-sfx-current.txt` — 27,603 B sha256 `9bcfecd6570dbc3334d616414fa27dfa9e40ee1ed4a6d6c977ae7812659372be`, header + full current file, verdict to bind to the current hash — and delegated it to surf in the same message that accepted the B4 FAIL.
     (b) UNPLANNED FIXED: new `GUARDS (sfx_policy + wav_guard; PASS in manifest, previously unplanned)` group in the plan (JSON 5,420 B, MD 7,186 B). Both files are hash-bound in `cb-A6a` (`sfx_policy` `5c3d2ce62a10…`, `wav_guard` `998b2cdfc9f7…`), so the group is genuinely reviewed: `landing-check.sh GUARDS` → `CHECK PASS`, rc=0. Re-checked the plan files: MD/JSON consistency 8/8 groups, 0 problems (receipt `d2905928f2071550…`); plan-vs-manifest 25 planned paths AGREE (receipt `426b0f70c915e1ec…`).
     (c) UNBOUND MENTIONS RESOLVED BY CONTENT IDENTITY, not by assertion: for `lora_pipeline.py`, `render_service.py`, and EL `cli.py`/`client.py`/`models.py`, the file's mtime PRECEDES its packet's build time and every `def`/`class` anchor appears in the packet (19/19, 16/16, 12/12, 18/18, 11/11), so the reviewer saw exactly the bytes that would land. Recorded in `outputs/coverage-decisions-20261112.json` (3,997 B sha256 `29b78af4e17c6b25…`).
     (d) POLICY EXEMPTIONS RECORDED, with content: EL `__init__.py` is 44 bytes of package docstring only (no code/imports/exports) → `NO_REVIEW_REQUIRED`; `uv.lock` is a dependency lockfile, not code, 111 skills track `uv.lock` on origin/main → lands with the EL group for reproducibility.
     Coverage receipt re-run as v4: 25 blocking paths, 25 planned, **17 REVIEWED + 5 REVIEWED_BY_CONTENT_IDENTITY + 2 POLICY_EXEMPT + 1 pending correction, `unresolved=[]`**, verdict `COVERAGE_RESOLVED_EXCEPT_PENDING_CORRECTION`. Receipt `outputs/packet-group-coverage.json` 6,015 B sha256 `36bea7f530bef77ca42bfe044648c758ec4a369bbcefb9efda52d009706e96e1`.
     Self-caught: three earlier matcher versions were wrong (v1 cross-attributed hashes between neighbouring names; v2 required repo-relative paths that packets never use; v3 counted basename mentions as coverage) — each was replaced because it produced a wrong claim, and the wrong versions are named in the v4 method field.

28. [x] B4 FAIL repairs — ALL 18 findings fixed and proven; re-review delegated as B4 pass 2.
     Sources: `speak_core.py` (sha `342744057172c96b…`, 45,007 B), `speak.py` (`7c238086b607f154…`, 35,428 B), `arc_chart.py` (`17ccab9c1e3b3172…`, 19,583 B), `test_core_contract.py` (`2c5d2c43803b248a…`, 25,826 B); harnesses `tests/test_prove4.py` `b7aedacd…`, `test_prove5.py` `35cd0d43…`, `test_prove6.py` `9772c6cc…`, `test_prove7.py` `82708176…`.
     B4a: SC-01 batch route no longer pre-opens by pathname and derives duration from verified bytes; no-procfs containment now fails CLOSED. SC-04/SK-10 one `_rendered_transcript(snapshot)` for chunk routes, validated by the receipt and shared with the analyzer; `build_plan` derives `answer_text` from chunks (the live proof hit a real 422 on the empty value). SC-09 full RIFF walk (declared extent, chunk bounds, even padding, fmt consistency, mid-frame data). SK-09 gate dedented out of the dead `else` and now includes the final text, answer text, and every chunk. SK-11 `spoken_text` strict, `original_text` provenance via recorded `text_transformation`, session file written only after a receipt exists. SK-12 session entry never resolved, symlinked entry refused, forced post-load swap leaves the other session byte-identical. SC-12 `O_NONBLOCK` before the regular-file check. SK-13 post-render extras under `caller_metadata` with full revalidation before write.
     Harness defects: PH-01 now drives the CLI (refusal-before-POST, control, receipt/analyzer transcript equality) — its control failed for a REAL reason first (`original_text=""` asserted as provenance) and was fixed; PH-02 compares the full ordered sequence plus reversed/duplicated/truncated controls; PH-03 holds turn_id fixed, requires the exact gain sequence `[-24.0, 6.0]`, and compares bodies after normalizing the render-uuid `label`; PH-04 renders real WAVs, compares real hashes, adds an unswapped control, scans published artifacts for the outside hash, and includes a mutant that restores the vulnerable pathname read; PH-05 supplies pace only at plan level.
     B4b: AC-02 scan mode protects every receipt it read (refusal verified, source hash unchanged, separate-output control passes). AC-06 destination directory opened once, bound descriptor verified via `/proc/self/fd`, destination identity re-checked under that descriptor, staging/publication dir_fd-relative — a forced parent swap inside `_write_all` leaves the protected input unchanged and the output in the BOUND directory. AC-07 partial final artifact unlinked on failure, staging cleaned on any failure. TC-02 replaced the mock oracle with a real threaded HTTPServer: exactly one request, sha256 of the bytes the SERVER RECEIVED matches the result and receipt digests, an independent hash of the frozen snapshot matches the recorded plan digest, plus two mutation controls.
     Verification: `tests/run.sh` rc=0 — 22/22, 16/16, 7/7, 14/14, 24/24; `sanity.sh` rc=0 ("retained harnesses OK", "negative control OK", live render OK); `test_core_contract.py` rc=0 `PASS_CORE_IMPORT_CONTRACT`.
     Packet defect fixed: `/tmp/cb-B4-pass2.txt` 19,951 B sha256 `0a4b338d1e140672676f6d618a914a90372558564f4f3219d7a10609fbd98a3e`, independently re-scanned 0 absolute host paths and 0 parent-relative paths; every repo path uses `<repo>/skills/...`. Delegated to surf over intercom with the hash and a per-finding verdict ask.
     Self-caught during proofs, recorded rather than hidden: the `original_text=""` chunk-route failure (my SC-11 gate exposing a CLI bug), the batch-response mock shape in PH-01 (my harness), the render-uuid `label` in PH-03 (surf-sanctioned normalization), and the SC-04 empty-`answer_text` 422 (production defect surfaced only by a live render).

29. [x] Landing plan/manifest refreshed — 8 rows updated, all four checks re-run, no stale-hash landability.
     Updated (`old -> new` prefix): `speak_core.py` `2d44ee89ffe4 -> 342744057172`, `speak.py` `7da5b7876eaa -> 7c238086b607`, `arc_chart.py` `dff58ead6663 -> 17ccab9c1e3b`, `test_core_contract.py` `dcf7da8718b0 -> 2c5d2c43803b`, `tests/test_prove4.py` `fd10d037ae20 -> b7aedacdaf80`, `test_prove5.py` `4b1e01ab1b15 -> 35cd0d4385d3`, `test_prove6.py` `3be999c90f3c -> 9772c6cc4272`, `test_prove7.py` `619999c0d63a -> 82708176a7c9`. Manifest rows also had `bytes` and added/removed line counts recomputed against `origin/main`.
     Artifacts: plan JSON 5,420 B sha256 `58628ff08c3305f1…`; plan MD 7,186 B `7d4ba72999e49ce4…`; manifest 18,287 B `40746e05b07b2554…`.
     Checks: `landing-plan-consistency.py` 8/8 groups, 0 problems, CONSISTENT. `landing-plan-vs-manifest.py` 25 planned / 28 manifest files / 3 landed, AGREE. `landing-check.sh` for all 8 groups reports **0** CHANGED / ORIGIN MOVED / MISSING rows: B4, A7, T1, T1b, EL, LP, render_service all rc=3 (correctly refused on the review gate), GUARDS rc=0, and the hash-only opt-out passes B4 rc=0 and T1 rc=0. Blocking count 25 (28 rows − 3 landed).
     **Real consequence found, not papered over:** the T1 packet (`cb-T1`) cites the PRE-repair harness hashes, so a T1 PASS alone can no longer unblock the four harnesses. Current coverage: `narrator_sfx_batch.py` and `test_packet_a7_reporting.py` are bound in `cb-T1`; `test_prove4..7.py` are bound in `cb-B4-pass2`. Coverage receipt v5 records this split explicitly: `summary={'REVIEWED': 13, 'REVIEWED_BY_CONTENT_IDENTITY': 5, 'REVIEWED_IN_B4_PASS2': 4, 'POLICY_EXEMPT': 2, 'STALE_HASH_CORRECTION_PENDING': 1}`, `unresolved=[]`, verdict `SPLIT_REVIEW_RECORDED`, sha256 `53554f1ffd7cf267902159bf075fc15c87fbf8c7fc9c63ba88d470dcbaee74aa`.
     Also confirmed `cb-B4-pass2.txt` cites exactly the manifest's current hashes for all four B4 sources, so a PASS on it binds to what would land.

30. [x] Verdict-citation binding gate added and mutation-controlled — a PASS can no longer come from a packet that reviewed a different artifact.
     `landing-check.sh` (sha256 `2ff0098c9af114dc6b88fd7f6059084fac2f82de3ad47ec7ef8747da46bb67d4`) now has a fourth gate: for every PASS/LANDED row it proves the verdict is BOUND. A recorded `review_packet` is authoritative and must exist and contain the row's CURRENT sha256; otherwise the `review_citation` is resolved to candidate packet files (literal path, basename, or a `surf-cb-XXX` report → `cb-XXX*.txt`) and one must contain the current hash. LANDED rows are instead verified against the `origin/main` blob. Unbound PASS rows print `CITATION UNBOUND …` and exit 3, separately from `REVIEW PENDING` and from hash failures.
     Manifest updated to record the real binding rather than infer one: `sfx_policy.py` and `wav_guard.py` now carry `review_packet=/tmp/cb-A6a.txt`, set only AFTER verifying each row's current sha256 appears in that packet (`5c3d2ce62a10…`, `998b2cdfc9f7…` indeed present). Manifest now 18,371 B sha256 `050bcde7bf8a302f3f7657b240ffdde6e845f62617ed6db461c3c56c1b87c552`. `landing-check.sh GUARDS` → `CHECK PASS`, rc=0.
     Mutation controls, on COPIES only (`/tmp/cite-check`), with the real files byte-verified afterwards:
     - M1 — B4 rows marked PASS with `review_packet=/tmp/cb-B4a.txt` (the PRE-repair packet): rc=3, four `CITATION UNBOUND … recorded review_packet cb-B4a.txt does not contain the current sha256 <current>` lines. This is exactly the failure mode the split exposed.
     - M2 — same rows marked PASS with `review_packet=/tmp/cb-B4-pass2.txt` (the current packet): rc=0 `CHECK PASS`.
     - M3 — PASS with empty citation and no recorded binding: rc=3, fail closed (`citation '' names no packet containing the current sha256 …`, candidates empty).
     Real artifacts unchanged by the controls: manifest `050bcde7…`, script `2ff0098c…`.

31. [x] Pre-bind audit done — every pending row now cites a packet that binds its CURRENT sha256, and the gate is proven to accept that the moment a verdict lands.
     Audit (read-only first) covered all 25 planned rows: 18 HASHED, 5 CONTENT_IDENTITY, 2 POLICY_EXEMPT, 0 UNBOUND, 0 rows outside a group. Stale citations found and replaced, each verified BEFORE writing (`assert current_sha in packet`):
     - B4 four sources -> `cb-B4-pass2.txt` (citations previously pointed at `cb-B4a`/`cb-B4b`, which bind pre-repair hashes).
     - T1 four harnesses (`test_prove4..7.py`) -> `cb-B4-pass2.txt` with an explicit SPLIT note: their PH-0x repairs were reviewed there, while `cb-T1` binds pre-repair hashes.
     - T1 remaining two (`narrator_sfx_batch.py`, `test_packet_a7_reporting.py`) -> `cb-T1.txt`.
     - T1b three (`sanity.sh`, `tests/run.sh`, `tests/.gitignore`) -> `cb-T1b.txt`.
     - A7 `interrupt_sfx.py` -> `/tmp/cb-A7-interrupt-sfx-current.txt` with the note that A7 itself binds the pre-refactor `0f85cb09`; `spyke_render.py`/`sfx_verify.py` -> `cb-A7.txt`.
     - CONTENT_IDENTITY five (`lora_pipeline.py`, `render_service.py`, EL `cli.py`/`client.py`/`models.py`) -> `review_binding={kind: content_identity, evidence: coverage-decisions-20261112.json}`.
     - POLICY_EXEMPT two (EL `__init__.py`, `uv.lock`) -> `review_binding={kind: policy_exempt, evidence: …}`.
     No verdict was changed: real verdict counts remain LANDED 3, PASS 2, PENDING 14, NOT REVIEWED 8, NO RECEIPT 1.
     Gate extended (`landing-check.sh` sha256 `31a5fa7a7c9cc1600e7d4375f149efac752610157798e6815db7ce4679351d35`): a `review_binding` is accepted only when its evidence file contains the row's current sha256 AND the specific marker (`REVIEWED_BY_CONTENT_IDENTITY` or `NO_REVIEW_REQUIRED`); otherwise it refuses like any unbound PASS.
     Manifest now 21,040 B sha256 `78b3f9911cde19e8bef541529cbaafa62cddf2f18c19654cc82cb713f717451b`; 18 rows carry `review_packet`, 7 carry `review_binding`.
     Mutation proof on COPIES (`/tmp/prebind`), `verdict=PASS (simulated)` on every pending row: **all 8 groups CHECK PASS, rc=0** (B4, A7, T1, T1b, EL, LP, render_service, GUARDS). M4 removed one row's citation and packet while leaving PASS -> rc=3 `CITATION UNBOUND … citation '' names no packet containing the current sha256 342744057172…`. So the bindings are complete AND the gate still fails closed.
     Re-checked after the manifest edits: `landing-plan-consistency.py` CONSISTENT (8/8), `landing-plan-vs-manifest.py` AGREE (25 planned / 28 files / 3 landed), `landing-check.sh GUARDS` rc=0, and real `landing-check.sh T1` still refuses on PENDING (6 files) rather than passing on a stale citation.

32. [x] Verdict→group unblock matrix BUILT, cross-checked, and made drift-proof — landing is now a lookup.
     Artifacts next to the landing plan: `verdict-unblock-matrix-20261112.json` (sha256 `f0d7d0e7a3f2f0d6…` reported below from the read-back) and `verdict-unblock-matrix-20261112.md`. Built only from the plan + the manifest's recorded `review_packet`/`review_binding` values; no verdict was inferred.
     Groups and the verdicts they need:
     - B4 → `cb-B4-pass2` (4 paths).
     - A7 → `cb-A7` (2: spyke_render, sfx_verify) **plus** `cb-A7-interrupt-sfx-current` (1: interrupt_sfx) — two verdicts, because A7 itself binds the pre-refactor hash `0f85cb09`.
     - T1 → `cb-B4-pass2` (4 harnesses `test_prove4..7.py`) **plus** `cb-T1` (2: narrator_sfx_batch, test_packet_a7_reporting) — two verdicts; `cb-T1` alone can no longer unblock T1.
     - T1b → `cb-T1b` (3). EL → `cb-el-1` (5, all via recorded bindings). LP → `cb-lp-1` (1). render_service → `cb-rs-1` (1).
     - GUARDS → `landable_now=True` (both rows already PASS and hash-bound in `cb-A6a`).
     `needs_two_verdicts = [A7, T1]`.
     Cross-check: planned=25, paths_with_target=23, `unbound_planned=[]`, `mismatches=[]` (the other 2 are the PASS rows in GUARDS, which are already covered and deliberately not waiting on a packet).
     Retained checker `verdict-unblock-matrix-check.py` recomputes the mapping and compares it to the stored matrix: `MATRIX_CONSISTENT`, receipt sha256 `428893933937acb91092592a6a3b8ef2276c1e317cbf95c26ff64ab1d1116799`, rc=0. Mutation control on a copy pointing B4's rows at `cb-B4a` (stale packet) → rc=1 with the per-row mismatch lines.
     Two real gaps the checker caught in my own work, both fixed rather than loosened: (1) my first checker compared content-identity rows against `review_packet`, which those rows deliberately do not carry — it now compares `review_binding.kind` and requires the citation to name the packet; (2) seven binding rows still said "surf queue"/"EL packet (surf queue)" instead of naming their packet, so their citations were updated to name `cb-el-1`/`cb-lp-1`/`cb-rs-1` explicitly. Manifest now 21,171 B sha256 `334057255297cab93bc0bf10480a318d405215db61f3f2b95372940c2e0f81bf`; the matrix's `generated_from.manifest_sha256` was refreshed to match, which is what the checker verifies.

33. [x] Landed 1 of the 2 GUARDS files; the second was correctly refused — blocking dropped by 1 (25 -> 24), not 2, because the item's premise was wrong for `wav_guard.py`.
     LANDED: `scripts/sfx_policy.py` (9,194 B sha256 `5c3d2ce62a1034850df60f48b184afa57361fb5d3212875f55a1e0d133ab293a`) as commit `1d368faed377fb6fa112a4ee696fb5b440df7380`. Verified `git show origin/main:…` == the recorded sha256. Reviewer receipt `/tmp/receipt-sfx-policy.json` (1,153 B sha256 `e2c253a61d972d2ee9691f2814ea31ff5c7cf6bd1b7989e7a5094045675467f4`) built from the real A6 evidence — packet `cb-A6a` contains the artifact hash AND the report states `VERDICT sfx_policy.py: PASS` — validated by `gh-land/reviewer_receipt.py` (`{"valid": true, "reviewer_provider": "openai"}`, rc=0). Live effect read-back quoted in the receipt: `PASS sfx_policy (0 problem(s))`, rc=0.
     REFUSED (and now correctly blocked): `scripts/wav_guard.py`. Its manifest PASS came from A5 (`VERDICT wav_guard.py: PASS`), but the current artifact sha256 `998b2cdfc9f7f423…` appears in NEITHER A5 packet; `cb-A6a` contains that hash yet states no verdict for the file (A6 mentions `wav_guard` only as an unused import sentinel). So there is no verdict bound to the bytes that would land. It remains absent from `origin/main` (verified).
     State after: manifest 21,433 B sha256 `29ac1b4124981637c62b5d14e4fcbfb963d7369631cc39f9cb052109bbcd1e71`; **4 LANDED, 24 blocking**; plan groups 8 (GUARDS renamed to `GUARDS-WAVGUARD (current bytes not yet reviewed; A5 PASS binds an older artifact)`); plan/JSON consistency CONSISTENT; plan-vs-manifest AGREE (24 planned / 28 files / 4 landed). Matrix regenerated (9,231 B sha256 `b3ddbdb181a46fca298b54c0ed4151c6538cde6b15a161f1d44a07cb7ee8a95d`), checker `MATRIX_CONSISTENT` (receipt `f562421597ea014a…`); `landable_now=[]`; `needs_two_verdicts=[A7, T1]`; `wav_guard` is recorded as needing a fresh review, so `unbound_planned` lists it deliberately rather than hiding it.
     Gate defect this exposed, FIXED: hash presence was treated as a verdict, which is exactly why `wav_guard` looked landable. `landing-check.sh` (sha256 `4d3c959befb56305e90e636306a92816820b90f613b71fad3cff4a9cfeb4b79d`) now also requires a `VERDICT … <file> … PASS` (or `<file> … : PASS`) line naming the file, in the packet or a cited report. Mutation controls on separate copies: M5 (PASS + hash in `cb-A6a`, no verdict) -> rc=3 "contains the current sha256 998b2cdf… but states no PASS verdict for wav_guard.py"; M6 (same row + a report containing `VERDICT wav_guard.py: PASS`) -> rc=0. Real manifest untouched (`29ac1b41…`).
     Self-caught error during that proof: the first M5 run passed because my M6 step mutated the SAME copy, so both runs used the citation with the fake verdict report; re-ran M5 and M6 on separate copies.

34. [x] SUPERSEDED: the fresh `wav_guard.py` packet (`/tmp/cb-wg-review.txt`, self-sha `181d05b5…`) is stale-by-bytes and the watcher reports its only response as `STALE_RESPONSE_SUPERSEDED` (`surf-cb-A6`). Live `scripts/wav_guard.py` is `998b2cdf…`; nothing was landed on the old PASS, which was the item's stated constraint and remains true.
     The review obligation itself is NOT dropped: a rebuilt packet at the current bytes is queued as item 101.

35. [x] Landing-gate rules RECORDED and LANDED — `80f1d4dd490dbe953b8740cf021ab2042384da92`.
     `skills/chatterbox-speak/references/verification-evidence.md` 7,467 B sha256 `128fc27d40dca6cbb04b897af0dd2f788bf6e34cd7c0e15e20f81726c1a270c2`; verified local == `git show origin/main:` byte-for-byte.
     New section "Landing gate — a hash inside a packet is not a verdict" (line 103) states the four rules with the concrete failures:
     - Rule 1 (line 109): hash presence in a packet is NOT a verdict, using the `wav_guard.py` case verbatim — current sha256 `998b2cdf…` sits in `cb-A6a` while A6 states no verdict for the file (sentinel mention only) and A5's PASS binds an older artifact. The gate requires a `VERDICT … <file> … PASS` line naming the file, in the packet or a cited report (line 115).
     - Rule 2: a verdict must bind the CURRENT bytes — a recorded `review_packet` must contain the row's sha256; LANDED rows verify the `origin/main` blob instead.
     - Rule 3 (line 125): content-identity and policy-exempt rows carry `review_binding={kind, evidence}` and are accepted only when the evidence file contains the current sha256 plus the specific marker.
     - Rule 4: T1's six files are split-reviewed (2 in `cb-T1`, 4 in `cb-B4-pass2`), and A7 needs both `cb-A7` and the `interrupt_sfx` correction.
     Also corrected the stale retained-gate counts in the same file to what the gate actually prints now: `test_prove4.py` 13/13 -> **16/16**, `test_prove5.py` 7/7 (unchanged), `test_prove6.py` 10/10 -> **14/14**, `test_prove7.py` 19/19 -> **24/24**, `packet_a7_reporting.py` 22/22 (unchanged). Grep for `13/13|10/10|19/19` across the skill's other `.md` files returns nothing, so the drift was contained to this file.
     Exit semantics documented with it: `landing-check.sh` returns 0 pass, 1 hash/origin mismatch, 2 usage, 3 review/citation refusal.

36. [x] Landing plan now teaches a command that can actually land, and the claim is proven in a disposable repo.
     PLAN (`outputs/landing-plan-20261112.md` 8,566 B sha256 `170f57dccb890f2a1c5ef1e94a946fd0517c521a6549edbe899f594f1b7cda07`; `.json` 7,128 B sha256 `22fd16b94a198c07b039057c386cf51b7c7021043278cd11fc1d3ac41fe3f76e`):
     - New "## Step 2 — reviewer receipt (required for every `.py` path)": write the receipt (reviewer/author families must differ; all four invariants; non-empty `effect_readback.command` AND `.result_quote`; `greenfield=true` + `requirement_restatement` when any path is absent on `origin/main`), validate with `reviewer_receipt.py`, then run the group command — which now already carries the flag.
     - Exactly one `--reviewer-receipt /tmp/receipt-<slug>.json` added to each source group: B4, A7, T1, EL, render_service, LP, GUARDS-WAVGUARD. `T1b` (.sh/.gitignore only) deliberately has none.
     - JSON `_meta` records the three-step procedure, `groups_requiring_receipt`, `groups_without_receipt`, and a pointer to the gate-rules doc. Both plan checkers were updated to skip `_meta` (it is not a group) and re-run: consistency CONSISTENT (receipt `d2905928…`), plan-vs-manifest AGREE (receipt `7fa25bb7…`), matrix MATRIX_CONSISTENT (receipt `f5624215…`).
     PROOF in a disposable repo `/tmp/landing-shape` (bare origin; gh-land + ops-worktrees land.sh copied in; no real remote touched):
     - A: `.py` with NO receipt -> rc=1, `gh-land: REFUSED — source file(s) (probe.py) require a cross-provider reviewer receipt.`
     - B: the SAME `.py` WITH a valid receipt -> rc=0, `gh-land: reviewer receipt OK — {"valid": true, "reviewer_provider": "openai"}`, landed `c5d271e1bdf475a9d50f58a6348865f2626fa09d on origin/main` (probe origin).
     - Mutants all rc=1 with named reasons: m1 `missing required invariants: names_prove_claims`; m2 `provider_inequality: reviewer_provider must differ from author_provider (both 'openai')`; m3 `requirement_restatement: required non-empty when greenfield=true`.
     Evidence preserved outside `/tmp`: `outputs/landing-shape-proof/` (9 files, `MANIFEST.json` sha256 `67cd53210c2555dfc65b009b4e538d813f8345d7e6c54e5febd0478f0da414dd`), which states its boundary — it proves the documented shape against gh-land's own gate, while live acceptance remains the real `sfx_policy` landing `1d368faed3`.
     Retained checker `outputs/plan-receipt-step-check.py`: `PLAN_TEACHES_LANDABLE_COMMANDS`, receipt sha256 `5d5744d8c6cbe0abc8ef2a961953c65ec0c1d694de6874bc5ea5b12588307992`, rc=0. Mutation control on a copy (strip B4's flag) -> rc=1 naming `B4: 0 --reviewer-receipt occurrence(s)`.
     Harness note: the global agent-skills git guard blocked the probe's raw upload as designed. I did not bypass it — the probe's `origin/main` was created by fetching the commit into the bare repo, and only gh-land's own sanctioned landing path wrote anything (inside the probe).

37. [x] Plan's "Already landed" block now mirrors the manifest, and the two commit-less rows were given their real commits.
     `outputs/landing-plan-20261112.md` 9,017 B sha256 `ac3ff28a729106095ff71bcc63f8fa9b0e8eea93a3041a69c40a0dec1d2c612d`. The block now reads, in manifest order:
     - `PARKED.md` LANDED `06944695df`
     - `SKILL.md` LANDED `6981fe3fe2`
     - `references/verification-evidence.md` LANDED `80f1d4dd49` (was mis-cited as `35057c53d8`, the pre-gate-rules commit)
     - `scripts/sfx_policy.py` LANDED `1d368faed3` (previously absent)
     and states it is derived from the manifest's LANDED rows, so the next landing updates it by re-deriving rather than by memory.
     `outputs/landing-manifest-20261112.json` 21,659 B sha256 `ef75c3e1d0b14c4e00c1473b87cf0ee3359b75f04291320942570926ebc5bc02`: all 4 LANDED rows now carry `landing_commit` (previously `SKILL.md` and `verification-evidence.md` had none, and `PARKED.md` carried its commit only inside the verdict string), so "LANDED" is no longer an unbound claim.
     Re-ran the named checkers: `landing-plan-consistency.py` CONSISTENT (rc=0) and `landing-plan-vs-manifest.py` AGREE (rc=0; plan paths checked=24, manifest files=28, planned=24, landed=4). Because the manifest and plan bytes changed, the matrix provenance was refreshed and re-verified: MATRIX_CONSISTENT (matrix 9,231 B sha256 `22f89e713da9e28137a721d92f4aaa3b7b2ec401850c704d08f48e277b2201f5`), and `plan-receipt-step-check.py` still returns PLAN_TEACHES_LANDABLE_COMMANDS.
     Guard check after the edits: all eight groups still refuse (B4, A7, T1, T1b, EL, LP, render_service, GUARDS-WAVGUARD — every one rc=3), so nothing was silently unblocked by the doc change.

38. [x] Board drift snapshot BUILT and PROVEN, and it immediately caught a real stale row.
     `outputs/board-drift.py` (retained) reads `landing-manifest-20261112.json` and classifies every row against the bytes on disk and the cited evidence: `LANDED_BLOB_MATCH` (origin/main blob == recorded), `BOUND` (packet contains the recorded hash and disk == recorded), `BOUND_BY_BINDING` (binding evidence contains the hash + marker and disk == recorded), `AWAITING_REVIEW` (no packet because nothing has been reviewed — an honest state, not drift), `PACKET_MISSING`, `PACKET_LACKS_CURRENT_HASH`, `HASH_CHANGED_SINCE_PLAN`, `BINDING_EVIDENCE_MISSING`.
     REAL DEFECT FOUND AND FIXED: `references/verification-evidence.md` was recorded as `a2a1e7b9…` while both disk and `origin/main` held `128fc27d…` (the gate-rules landing `80f1d4dd49` happened after the row was written). The row's sha256 was updated to the landed blob with a citation naming that commit. Manifest now 21,724 B sha256 `6435911eaa6f0fce2625029815a2bf2217b744e71e5b85f87d09061879603c63`.
     `outputs/board-drift-20261112.json`: 28 rows -> `LANDED_BLOB_MATCH` 4, `BOUND` 16, `BOUND_BY_BINDING` 7, `AWAITING_REVIEW` 1 (`wav_guard.py`, item 34), zero problems, verdict `BOARD_BOUND`, rc=0, receipt sha256 `46094ab1395f0775d68f923ef815f27bb0e7b3488b7b2e0bf989220d18c12039`.
     Mutation control on a throwaway copy with `sfx_verify.py`'s recorded hash corrupted: `HASH_CHANGED_SINCE_PLAN` for exactly that row, verdict `BOARD_DRIFTED`, rc=1.
     All four plan guards still pass after the fix: consistency CONSISTENT, plan-vs-manifest AGREE (24 planned / 28 files / 4 landed), matrix MATRIX_CONSISTENT, plan-receipt-step-check PLAN_TEACHES_LANDABLE_COMMANDS; matrix provenance refreshed to the new manifest sha.

39. [x] Regression gate PASSED against the current tree (sfx_policy landed, docs landed, wav_guard unlanded) — counts match the doc exactly, so no doc fix was needed.
     `./tests/run.sh` -> **rc=0**, `tests: all retained harnesses PASS`, with the observed counts:
     - `test_packet_a7_reporting.py` 22/22
     - `test_prove4.py` 16/16
     - `test_prove5.py` 7/7
     - `test_prove6.py` 14/14
     - `test_prove7.py` 24/24
     These are exactly the five numbers `references/verification-evidence.md` now claims (16/16, 7/7, 14/14, 24/24, 22/22), so the doc I landed is accurate rather than optimistic.
     `./sanity.sh` -> **rc=0**. Self-checks: pronounce PASS, pauses PASS, cover_plan PASS, `joke_search PASS (49400 safe jokes, backend=local_corpus)`, filler_gain PASS, `hum_render PASS (17 songs; bed=acompressor=threshold=-20dB:ratio=3:attack=20:release=250,loudnorm=I=-20:TP=-1.5:LRA=7)`, `conversation_arc PASS (grief: 9 elements, 37920ms covers 30000ms; hum bed + reassure arc)`, `arc_scenarios PASS (12 scenarios; tiers ['complex','medium','simple']; all plan + build render steps)` — and sanity also re-runs the retained harness gate with the same five PASS lines.
     Receipts written by the run (gitignored, `tests/receipts/`): packet_a7_reporting 3,325 B `b6ef4289010beb97…`, prove4 2,046 B `6308b7f987def0b9…`, prove5 1,118 B `d2babd9964d56e69…`, prove6 1,923 B `4b882741c0c44194…`, prove7 2,962 B `cbf60209aa7a3be0…`.
     Nothing was "fixed" to make the numbers match: they were observed, then compared. Boundary: this is the local tree; it does not re-prove the live engine at `:8018` or any SFX library verdict.

40. [x] Evidence archives verified against their own manifests — all intact, and the verifier is proven to catch damage.
     `outputs/archive-integrity.py` normalizes the three different manifest shapes (packets = list of `{file,bytes,sha256}`; MVP4 + landing-shape = `{relpath:{bytes,sha256}}`), and also flags any file on disk with no recorded hash as `UNRECORDED`, because such a file cannot be cited.
     Real run, `outputs/archive-integrity-20261112.json` sha256 `b5ac60cba6eff0428cb4918bd52b3405a8f4ea3c90f9f01ad0cfd7d8b2a2bdd8`, verdict `ARCHIVES_INTACT`, rc=0:
     - `packets-20261112` INTACT — 5 files, 5 MATCH (`cb-B4a`, `cb-B4b`, `cb-A7`, `cb-T1`, `cb-T1b`).
     - `el-sigh-lora-mvp4-20261112` INTACT — 22 recorded files, 22 MATCH. Accounting for the item's "23": the 23rd file is `AUDIT.json` itself, which IS the manifest, so 22 recorded + the manifest = the 23 preserved files.
     - `landing-shape-proof` INTACT — 9 files, 9 MATCH.
     Mutation control: copied `packets-20261112` to `/tmp/arch-mut`, appended one byte to `cb-T1b.txt` -> `COMPROMISED`, counts `{MATCH: 4, HASH_MISMATCH: 1}`, the flagged list is exactly `['cb-T1b.txt']`, verdict `ARCHIVE_DAMAGED`, rc=1. Positive control on the unmutated copy -> `ARCHIVES_INTACT`, rc=0.

41. [x] SUPERSEDED chain closed: pass-8 (and passes 9–13c) are all overtaken by the applied verdicts. A7 pass-13c FAIL was applied and repaired (items 88/91/92), pass-14 was applied (item 96), pass-15 was applied and repaired (items 97/99), and **A7 pass-16 (`d78b86c1…`) is the only live A7 packet**. No pass-8 verdict may be applied to current bytes.
     Evidence: `verdict-intake` runs for 13c/14/15 are recorded in the doc; pass-16 is delegated and pending (item 100). No work remains under this item.

42. [x] Landing hygiene for the A7 repairs DONE, with one real drift found and correctly demoted rather than rebound.
     A7 group now carries the REPAIRED bytes and the new harness, all `NOT REVIEWED (current artifact)` with NO `review_packet` — deliberately not bound to the pass-8 packet while its verdict is pending:
     - `scripts/sfx_verify.py` `b35fa49ac57306bb…` (39,765 B)
     - `scripts/spyke_render.py` `97cef036c52c22a7…` (28,422 B)
     - `scripts/interrupt_sfx.py` `4911df2fbf79c294…` (30,508 B)
     - `tests/test_prove8.py` `1bf92804b19231f1…` (19,979 B, new path)
     DRIFT FOUND AND FIXED: wiring `test_prove8` into `tests/run.sh` changed that file (`9701df1f…` -> `9fa3ae51…`), and its cited `cb-T1b` packet binds the OLD bytes. Rather than rebind it to a packet that reviewed different content, the row is now `NOT REVIEWED (current artifact)` with the reason recorded, and the matrix shows T1b as `AWAITING_VERDICT(t1b-pass8)` plus `cb-T1b` for the two files that packet still binds correctly.
     Checker defect this exposed: `verdict-unblock-matrix-check.py` compared awaiting rows against `review_packet` and called the honest state drift. It now requires that an `AWAITING_VERDICT(...)` row carries NO packet and NO PASS/LANDED verdict — the inverse check, so the state cannot be faked into "reviewed".
     Another self-caught break: the new `test_prove8` manifest row lacked `origin_main_sha256`, which made `landing-plan-vs-manifest.py` die with `KeyError` instead of reporting drift; the row now carries the same field set as every other row.
     Doc: `references/verification-evidence.md` 7,659 B sha256 `59abcb866200159f66…` adds the `test_prove8.py 23/23` line to the retained gate, LANDED `9bf0297db39ff5d2f04c149e101fecbbd5951098`; local == `origin/main` blob verified. The manifest's LANDED row and the plan's "Already landed" block were updated to that commit so they cannot cite the older doc.
     Final state and guards, all rc=0:
     - plan JSON 7,313 B `12cf65afdb42cb51…`; plan MD 9,204 B `0416e9e59f51bbff…`; manifest 22,751 B `0beae430bfb3b4f9…` (29 rows: 4 landed, 25 blocking); matrix 9,245 B `a2c1f184f088d1a5…`.
     - `landing-plan-consistency.py` CONSISTENT; `landing-plan-vs-manifest.py` AGREE; `verdict-unblock-matrix-check.py` MATRIX_CONSISTENT; `plan-receipt-step-check.py` PLAN_TEACHES_LANDABLE_COMMANDS; `board-drift.py` BOARD_BOUND.
     - board summary: LANDED_BLOB_MATCH 4, BOUND 12, BOUND_BY_BINDING 7, AWAITING_REVIEW 6 (the five awaiting-verdict paths plus `wav_guard.py`). `landable_now=[]`.

43. [x] Coverage v6 BUILT: every one of the 25 blocking paths is accounted for, zero silently uncovered, and the classifier is proven to fail when coverage is dropped.
     `outputs/packet-group-coverage-v6.json` sha256 `e2a241a16eef6442767074fc491690e50310b657b2b934e270f74c0cefd698d4`, verdict `COVERAGE_COMPLETE`, rc=0:
     - **BOUND_WITH_VERDICT 0** — honest: no row currently has a verdict bound to its current bytes (`sfx_policy.py` is LANDED and therefore out of scope here).
     - **AWAITING_DELEGATED_PACKET 18** — a named packet exists on disk, contains the row's CURRENT sha256, and the registry shows it was delegated.
     - **POLICY_BOUND 7** — content-identity/policy exemptions whose evidence file contains the current sha256 plus the specific marker.
     - **UNCOVERED 0.**
     Packets still owed, per group: A7 `cb-A7-pass8.txt`; B4 `cb-B4-pass2.txt`; GUARDS-WAVGUARD `cb-wg-review.txt`; T1 `cb-B4-pass2.txt` + `cb-T1.txt`; T1b `cb-T1b-pass8.txt` + `cb-T1b.txt`.
     Delegation registry written as `outputs/delegations-20261112.json` (sha256 `bff8c51655a55fa0…`): 7 packets, every one present on disk, plus an explicit path->packet `awaiting` map so "no verdict yet" cannot masquerade as coverage.
     One real gap closed on the way: `tests/run.sh` changed after `cb-T1b` reviewed it (wiring `test_prove8` into the gate), so it had NO packet that binds its current bytes. Built `/tmp/cb-T1b-pass8.txt` (1,947 B sha256 `d9394cea9c8f7ae1e63c52277e845d3b9291687c8f10147471923ce4cac35990`, 0 host paths, 0 parent-relative paths, current sha bound) and delegated it to surf; the row is now `AWAITING_DELEGATED_PACKET` instead of uncovered.
     Mutation controls on faithful throwaway copies:
     - M1 drop the `sfx_verify.py` awaiting marker -> counts `{AWAITING 17, POLICY_BOUND 7, UNCOVERED 1}`, the single UNCOVERED row is `sfx_verify.py` "no packet and no awaiting marker", rc=1.
     - M2 un-delegate `cb-B4-pass2` -> exactly the 8 rows it binds report UNCOVERED ("packet not delegated"): B4's 4 sources plus T1's `test_prove4..7.py`; rc=1.
     - Real receipt unchanged after both (`e2a241a1…`).
     Self-caught harness defect: my FIRST mutation copies held only the manifest/registry/plan/script, not `coverage-decisions-20261112.json`, so all 7 POLICY_BOUND rows failed with "evidence lacks the current sha256" — a copy artifact, not a coverage failure. Re-ran with the evidence file present so each mutation proves exactly one thing.

44. [x] Doc sweep DONE — no doc enumerates a stale harness list, and the landed blob already carries the sixth harness with counts that match a live gate run. Nothing needed landing.
     Sweep receipt `outputs/harness-doc-sweep-20261112.json` sha256 `4c01b94f8f399aa064b0e1d68e150de71c4eddb5745050de5d7b3eaafa189c51`, verdict `DOCS_MATCH_GATE`, 0 problems, across 91 `.md` files:
     - Live gate counts: `test_packet_a7_reporting.py` 22/22, `test_prove4.py` 16/16, `test_prove5.py` 7/7, `test_prove6.py` 14/14, `test_prove7.py` 24/24, `test_prove8.py` 23/23.
     - Doc claims: exactly those six, each appearing once, each equal to the live count. Harnesses absent from the docs: none.
     - `five`/`5 harness` matches about the gate: **0**. The 5 remaining "five" lines are unrelated (reply-plan coverage, a DESIGN object, PARKED requirements).
     Landed-blob verification (not the local file): `origin/main:skills/chatterbox-speak/references/verification-evidence.md` sha256 `59abcb866200159f66…` equals the local doc, and its retained-gate block lists all six harnesses including `test_prove8.py 23/23` (landed under item 42 as `9bf0297db3`).
     Also checked the doc's own honesty about main: line 63 carries the 2026-11-12 status note that the harnesses live in this project's working tree, and `tests/run.sh` is indeed still ABSENT from `origin/main` (T1 group unlanded) — so the doc does not send a reader on main to a file main does not have.

45. [x] Live path verified on POST-EDIT code — the running renderer really did hold pre-edit `spyke_render`, so a restart was required and was proven by the artifact, not by a 200.
     Process/module state BEFORE: only one process ran any of the changed scripts — pid **4151987**, `python3 scripts/render_service.py`, started **Thu Nov 12 10:29:57 2026**, while `spyke_render.py` was edited **14:04:04**, `sfx_verify.py` **14:05:07**, `interrupt_sfx.py` **14:05:51**. It imported `from spyke_render import ALLOWED_TONES, VOICE_PATHS, render_turn` at module load, so it was serving stale code. The engine is a separate container (`embry-voice-chatterbox-1`, Up 2 days, healthy, `127.0.0.1:8018->8018`) and does not import these scripts.
     RESTART: killed 4151987, started pid **3597212** at **14:12:13**, `/health` -> 200 after 2 tries; log `chatterbox-render listening on http://127.0.0.1:8799`.
     Engine independent check: `GET :8018/health` -> 200 with `{"ok":true,"mocked":false,"live":true,"engine":"chatterbox_turbo","model_loaded":true,"started_at_utc":"2026-11-10T15:24:16Z"}`.
     Real render: `POST :8799/render` `{"text":"Live path check after the A7 repairs.","speaker":"alex","thread":"general","seq":1,"eid":"a7live01"}` -> **200**, receipt `spyke.render_receipt.v1`, artifact `/mnt/storage12tb/embry-voice/turns/a7live01_alex_general_1.wav`.
     Nine independent checks, all PASS (a 200 is not proof):
     - `ok` true; `voice` = `alex` (the requested speaker's voice); `persona_simulated` true.
     - `text_sha256` = `958113475aea3b849ea2931b777bd53c1f0d5ad6a06fed033675cadfeb0d4be8` = sha256 of the posted text.
     - WAV exists at the receipt path; bytes 124,878; RIFF/WAVE; **62,400 frames** at 24 kHz mono 16-bit (2.6 s).
     - `audio_sha256` = `c0c527c48e9e8abc31e2239c717fafd2ee59027236ba5e53535e5eddc151e6c2` = sha256 of the file on disk; `wav_bytes` equals the real size.
     My first attempt returned **400** and that was my request's fault, not a service defect: `eid` `"a7live-20261112"` violates the service's `[A-Za-z0-9]{1,12}` rule. Re-posted with `eid=a7live01`.
     Boundary: this proves the LIVE render path (service -> engine -> WAV -> receipt/text binding) runs post-edit code. It does not re-prove library SFX quality, and the engine emits 24 kHz for this route while library masters are 44.1 kHz.

46. [x] Verifier slice check on REAL library data PASSED, with the publish-once half proven rather than assumed.
     Command (the interpreter that actually has `faster-whisper`): `/home/graham/miniconda3/bin/python3 scripts/sfx_verify.py --id alex-chuckle --id alex-clear-throat --id alex-cough-clear --out /tmp/slice/report1.json`.
     RUN 1: **rc=0**. `3/3 PASS (MECHANICAL gates only - not proof of content)`; each row's content gate is `CHECKED` with `failures=0` and `needs_human=False`:
     - `alex-chuckle` PASS, `alex-clear-throat` PASS, `alex-cough-clear` PASS.
     Report `/tmp/slice/report1.json`, 1,897 B, sha256 `0f179c22755669358527f6f38d0648d80a4d60126205a82fc5359b848ac8c2c1`. `grep -c Traceback` on the run output = **0**, so the edited parser/preflight raised nothing on live data.
     RUN 2 (publish-once): the same `--out` with one `--id` -> **rc=2**, message `--out /tmp/slice/report1.json already exists; refusing to overwrite an existing file (a report is publish-once evidence: choose a fresh --out)`, and the existing report's sha256 is unchanged (`0f179c22…`), so the refusal did not mutate evidence.
     MANIFEST COMPARISON: all three ids have manifest `status=awaiting_owner_verdict`, which is consistent with a mechanical PASS awaiting a human verdict; PASS rows carry no recorded failures. Receipt-level result: `SLICE_MATCHES_MANIFEST`.
     Boundary: three clips, ASR on, mechanical gates only. Event identity remains UNVERIFIED, and this is not the full 83-clip re-verification the item explicitly excluded. The report is still in `/tmp`, which item 47 fixes.

47. [x] Slice evidence RETAINED out of `/tmp` with per-file hashes and a verified copy step.
     `outputs/verify-slice-20261112/` now holds `report1.json`, `run1.out`, `run2.out` plus `MANIFEST.json` (2,200 B sha256 `c37049efbe9ed743888d52fe8e3894d90bbe5a7e4e1e7498152063ca06367caf`).
     Copy verification (source hash vs copy hash, taken after each copy):
     - `report1.json` `0f179c22755669358527f6f38d0648d80a4d60126205a82fc5359b848ac8c2c1` -> identical
     - `run1.out` `b940f0b8054859b7a0ef5952c6cc5435e40dd4d44d0760b4b8416a2da8901dc3` -> identical
     - `run2.out` `176026888f1c930bb51defad5f22f88e16217a553df61a710d90155126978338` -> identical
     The manifest records, per the item: the three ids (`alex-chuckle`, `alex-clear-throat`, `alex-cough-clear`), the interpreter (`/home/graham/miniconda3/bin/python3`, the one with `faster-whisper`), the exact command, run 1 (`rc=0`, `3/3 PASS (MECHANICAL gates only - not proof of content)`, per-id verdict/content-gate/failure counts, `tracebacks=0`), run 2 (`rc=2` plus the verbatim refusal text and `existing_report_unchanged=true`), and the manifest comparison (`SLICE_MATCHES_MANIFEST`: all three are `awaiting_owner_verdict`, consistent with a mechanical PASS awaiting a human verdict).
     Independent re-hash AFTER the manifest was written (not trusting the copy step): zero mismatches across all three files -> `RETAINED_AND_VERIFIED`.
     Boundary stated in the manifest itself: three clips, ASR on, mechanical gates only; **event identity UNVERIFIED**; not the full 83-clip re-verification.

48. [x] Archive integrity now covers the FOURTH archive, all four verified INTACT, and the new one is proven to catch damage.
     `outputs/archive-integrity.py` extended to 4,113 B sha256 `1984fa0cc7013788b381f677292a32c32142866b168755fa374f98a3fc94abfc` (adds `verify-slice`: dir `verify-slice-20261112`, manifest `MANIFEST.json`, dict shape).
     Real run, receipt `outputs/archive-integrity-20261112.json` sha256 `a80b19a170b67707fa7aa7dcc34460532b4ed0f938c76202b9cff693bc6f004c`, verdict `ARCHIVES_INTACT`, rc=0:
     - `packets` INTACT — 5 files, 5 MATCH
     - `mvp4` INTACT — 22 files, 22 MATCH
     - `landing-shape` INTACT — 9 files, 9 MATCH
     - `verify-slice` INTACT — 3 files, 3 MATCH
     This confirms the other three are still INTACT, so the receipt now describes the whole set rather than a three-archive subset.
     Mutation control on throwaway copies:
     - Positive control (unmutated copy): `verify-slice` INTACT 3/3 MATCH, rc=0 (receipt `509a6875…`).
     - Appended one byte to the COPY of `report1.json`: `COMPROMISED`, counts `{HASH_MISMATCH: 1, MATCH: 2}`, flagged list exactly `['report1.json']`, `run1.out`/`run2.out` still MATCH, verdict `ARCHIVE_DAMAGED`, rc=1 (receipt `66b446e1…`).
     Real archive untouched by the mutation: `report1.json` still `0f179c22…`, real receipt still `a80b19a1…`.
     Same-turn board sweep after the change, all rc=0: plan consistency CONSISTENT, plan-vs-manifest AGREE, matrix MATRIX_CONSISTENT, plan-receipt-step PLAN_TEACHES_LANDABLE_COMMANDS, board-drift BOARD_BOUND, coverage v6 COVERAGE_COMPLETE, archive-integrity ARCHIVES_INTACT.

49. [x] Verdict intake is now mechanical and all-or-nothing, proven to REFUSE four ways and ACCEPT one way without touching the real manifest.
     `outputs/verdict-intake.py` sha256 `a3bd07f97577736e1a8d4bc53aac3f79886f3119902d040560a5e0697cfab2cc`. Behaviour: parses `VERDICT <file>: PASS|FAIL` lines; every row it would flip must be named PASS **and** the report must contain that row's CURRENT sha256; any FAIL, unmentioned file, unknown file, hash-unbound PASS, or contradictory duplicate verdict refuses the WHOLE intake with no rows changed. It validates the prospective manifest on a COPY by running `landing-check.sh <GROUP>` against it, and writes the real manifest only if that gate passes (and only with `--apply`).
     Refusals, each on a throwaway copy (`--apply`, so a weaker tool would have written):
     - forged PASS (`VERDICT sfx_verify.py: PASS`, no hashes): rc=1, `sfx_verify.py: report does not contain its CURRENT sha256 b35fa49ac573… (stale/hash-unbound verdict)` plus the three unmentioned files; copy sha unchanged (`0beae430…`).
     - FAIL line: rc=1, `sfx_verify.py: verdict is FAIL`; unchanged.
     - missing file (no verdict line for `test_prove8.py`): rc=1, `test_prove8.py: no verdict line in the report`; unchanged.
     - contradictory duplicates (`PASS` then `FAIL` for the same file): rc=1, `REFUSED: contradictory verdicts for sfx_verify.py`; unchanged.
     Acceptance: a report containing all four A7 current hashes plus matching PASS lines -> `APPLIED: 4 row(s) -> PASS (report-genuine.txt)`, rc=0; each row carries `review_packet=/tmp/vi/report-genuine.txt`; the copy manifest became 22,625 B sha256 `42b4563908a16e8569e6b363c3b3b52c0bf8b48c28b0c18df84f48d22a5b8155`; `landing-check.sh A7` on the accepted copy returned `CHECK PASS A7` rc=0, so an intake that applies is one the gate accepts.
     Real manifest untouched across every proof: before `0beae430bfb3b4f9722ba4178931d0fc940dbd58c18e9cc6060b230af018bba1`, after identical. It was not run against the real manifest — no surf verdict has arrived for the repaired bytes.

50. [x] Mechanical intake DOCUMENTED and LANDED — `6905f0ca09c026ac8ad35fadae91b7b12f666ba9`.
     `skills/chatterbox-speak/references/verification-evidence.md` 8,939 B sha256 `37a32fad853480414c89e1be6d3180d06066d3deda0bd92d83029391e6d7db43`, new **rule 5 "Apply verdicts mechanically, never by hand"** (line 138), verified local == `git show origin/main:` byte-for-byte.
     The rule states the refusal conditions, the validate-on-a-copy-then-write rule, and that `--apply` is required:
     - refuses the whole intake on: a FAIL; a group file with no verdict line; a verdict on a file outside the group; a PASS whose report does not contain that row's CURRENT sha256; contradictory PASS/FAIL for the same file;
     - validates the prospective manifest on a **copy** by running `landing-check.sh <GROUP>`, and writes the real manifest only when that gate accepts the copy (`--apply` required; otherwise dry run);
     - cites the 2026-11-12 proofs: forged PASS rc=1 `report does not contain its CURRENT sha256`, genuine four-row PASS applied and the accepted copy then passed `landing-check.sh A7`.
     Discrepancy recorded rather than smoothed over: the item said "four refusal conditions", but the shipped helper has **five** (the fifth is contradictory duplicate verdicts, which I refused in the proof run). The doc states the true five, because documenting four would have left the contradictory case undescribed.
     Records updated so nothing cites the older doc: manifest 22,734 B sha256 `737f480b994ef35d4123e6914c024bc31d552847d12028379ff54d0b69300a2b` (LANDED row: sha, bytes, commit); plan MD `831d7c761fd01a62…` with the "Already landed" line now `6905f0ca09`.
     Board after the landing, all rc=0: plan consistency CONSISTENT, plan-vs-manifest AGREE, matrix MATRIX_CONSISTENT, plan-receipt-step PLAN_TEACHES_LANDABLE_COMMANDS, board-drift BOARD_BOUND, coverage v6 COVERAGE_COMPLETE, archive-integrity ARCHIVES_INTACT.

51. [x] Rule 4 corrected and LANDED — the A7 split is recorded as superseded by the pass-8 resubmission, T1's split left intact, and the matrix/plan deliberately untouched.
     `skills/chatterbox-speak/references/verification-evidence.md` 9,420 B sha256 `3f023ad19780d4e8cf0b33b36436e12ab605978ef71c63a1649de59c46921111`, LANDED `aa908042f5f081c1c217da2a820202d214115bf7`; local == `git show origin/main:` byte-for-byte.
     Rule 4 now says, in order: T1's six files are split (`narrator_sfx_batch.py` + `test_packet_a7_reporting.py` in `cb-T1`; `test_prove4..7.py` in `cb-B4-pass2`) and one packet alone cannot unblock T1 — that half is unchanged and still true. Then: A7 also needed two verdicts while its repairs were pending (`cb-A7` + `cb-A7-interrupt-sfx-current`, because A7 cites the pre-repair `0f85cb09`), and **"That split is superseded."** The pass-8 resubmission (`/tmp/cb-A7-pass8.txt`, sha256 `68d744b168eb8c98…`) binds the current bytes of all four A7 files, so ONE pass-8 verdict unblocks A7.
     The doc's claims were checked against reality, not just written: packet exists and its sha256 is exactly `68d744b168eb8c98cdd6342847b1a38c0684c661bb553bf3b47232ee4cee3ea7`; all four current hashes are present in it (`sfx_verify b35fa49a…`, `spyke_render 97cef036…`, `interrupt_sfx 4911df2f…`, `test_prove8 1bf92804…`); the four manifest rows remain `NOT REVIEWED (current artifact)`.
     "Do not change the matrix/plan" honoured and verified: matrix A7 still requires only `AWAITING_VERDICT(a7-pass8)`, matrix T1 still requires `cb-B4-pass2` + `cb-T1`, and the plan's A7 group is still the same four paths.
     Records updated to the new doc commit so nothing cites the older blob: manifest 22,753 B sha256 `06b984aa1c6fd4d890595581a930ee02fb79208513513cb41d323f51ff3d7a8e` (LANDED row sha/bytes/commit); plan MD `7be951d8e0209d55…`; matrix provenance refreshed.
     All seven guards rc=0 after the landing: CONSISTENT, AGREE, MATRIX_CONSISTENT, PLAN_TEACHES_LANDABLE_COMMANDS, BOARD_BOUND, COVERAGE_COMPLETE, ARCHIVES_INTACT.

52. [x] Doc gate-claims are now MACHINE-CHECKED against the landed doc and live state, and the checker is mutation-proven.
     `outputs/landing-gate-doc-check.py` sha256 `f2cd376fe5651b82a7e26bbf664037d27db8714391fa9844d4fa729dcf15aa6f`. It reads the LANDED doc from `origin/main` by default (so a local-only edit cannot satisfy it), asserts local file == landed blob, and `--doc PATH` exists solely so a mutation control can run against a tampered copy.
     Real run: 21 checks, 0 problems, verdict `DOC_CLAIMS_MATCH_STATE`, rc=0; receipt `outputs/landing-gate-doc-check.json` sha256 `4498befcf576f2c0439d10848e70c423be67b1df59339fe7a36884e792460448`.
     What it actually binds (the receipt records the acknowledged values, not just booleans):
     - (a) matrix A7 requires exactly `["AWAITING_VERDICT(a7-pass8)"]`; rule 4 contains "superseded", does NOT contain the old "cannot unblock either group" sentence, and names `cb-A7-pass8`.
     - (b) `/tmp/cb-A7-pass8.txt` exists; the sha it cites prefix-matches the real full sha `68d744b168eb8c98cdd6342847b1a38c0684c661bb553bf3b47232ee4cee3ea7`; all four current A7 hashes (`b35fa49a…`, `97cef036…`, `4911df2f…`, `1bf92804…`) are present in it; and none of those four rows is already recorded PASS/LANDED.
     - (c) matrix T1 requires exactly `["cb-B4-pass2", "cb-T1"]` and rule 4 still states both.
     - (d) rule 5 names `verdict-intake.py` and that file exists; its sha256 `a3bd07f97577736e…` is recorded in the receipt.
     Mutation control: reinserted the OLD A7 split sentence into a copy and dropped the superseded wording -> 3 named problems (`no 'superseded' in rule 4`, `packet not named`, `no cited sha`), verdict `DOC_CLAIMS_DRIFT`, **rc=1** (receipt `5aa88c7e…`). Unmutated copy through the same `--doc` path -> rc=0 (receipt `fd2912be…`), and the landed doc still passes afterwards (receipt unchanged at `4498befc…`), so the failure came from the mutation and not from the override path.

53. [x] One-command board sweep BUILT and MUTATION-PROVEN in both directions — `outputs/board-sweep.sh` 2,017 B sha256 `4226955b2a4c0c97e3bf44a65ff414953753de66e9ee416f2521e3d037c9567f`.
     It runs the eight guards (`landing-plan-consistency.py`, `landing-plan-vs-manifest.py`, `verdict-unblock-matrix-check.py`, `plan-receipt-step-check.py`, `board-drift.py`, `packet-group-coverage-v6.py`, `archive-integrity.py`, `landing-gate-doc-check.py`), prints one PASS/FAIL line per guard with that guard's own verdict string, and exits non-zero if ANY fails. The guards are read-only; the sweep's only write is its combined receipt `outputs/board-sweep-receipt.json` (`BOARD_SWEEP_RECEIPT` overrides the path so a proof run cannot clobber the real receipt).
     GREEN: rc=0, all eight PASS — `CONSISTENT`, `AGREE`, `MATRIX_CONSISTENT`, `PLAN_TEACHES_LANDABLE_COMMANDS`, `BOARD_BOUND`, `COVERAGE_COMPLETE`, `ARCHIVES_INTACT`, `DOC_CLAIMS_MATCH_STATE`; combined receipt sha256 `83fbc6230b972a2530e3787690314419d8265b0ef8d53328ad51fdb1ac0548cc` with `verdict=BOARD_SWEEP_PASS`.
     MUTATION (throwaway copy, one guard replaced by a stub): **first attempt was WRONG and is recorded** — the stub was referenced as `$DIR/stub-fail.py`, so it never ran: `rc=2` "can't open file". The sweep did fail and did name it, but for the wrong reason, which proves nothing about a guard that executes and returns failure. Fixed by letting a guard entry be an absolute path (`case "$g" in /*) target="$g";; *) target="$DIR/$g";; esac`) and re-running with `/tmp/stub-fail.py` (which prints `VERDICT: STUB_FORCED_FAILURE` and exits 1): rc=1, line `FAIL /tmp/stub-fail.py rc=1 STUB_FORCED_FAILURE`, receipt `BOARD_SWEEP_FAIL` naming exactly that guard. Green re-run after the edit: rc=0 and the real receipt still `83fbc623…` (mutation left it untouched).

54. [x] One-command sweep DOCUMENTED and LANDED (twice — the first landing stated a false thing about the write surface, and that was corrected before this item was closed).
     `skills/chatterbox-speak/references/verification-evidence.md`, final 12,261 B sha256 `94cb8d83b14d628e649d15b32f4b2b03bc5f45ab9ee65b5f7a00140d323c32f0`, LANDED `c95da7ff221581d5e80f6b1955d282435a1f4c9a`; local == `git show origin/main:` byte-for-byte.
     New section "One-command board sweep" lists all eight guards with what each asserts (plan MD/JSON consistency, plan-vs-manifest hashes, group requirement vs recorded verdicts, plan teaches receipt-bearing commands, per-row disk/origin drift classification, every blocking path covered, four archives intact, and the doc's own gate claims vs matrix/packet/helper bytes), states the invocation and the non-zero-on-any-failure contract, and cites the green combined receipt sha256 `83fbc6230b972a2530e3787690314419d8265b0ef8d53328ad51fdb1ac0548cc` plus the stub mutation (rc=1, failing guard named).
     **Correction made before closing (first landing was `b47038657e`, superseded):** the section originally said "The guards are read-only. The sweep's only write is its combined receipt." That is false — every guard writes its own receipt JSON, and the coverage guard also writes `delegations-20261112.json`. Verified by grepping `write_text` and by listing the receipt files: `landing-plan-consistency.json`, `landing-plan-vs-manifest.json`, `verdict-unblock-matrix-check.json`, `plan-receipt-step-check.json`, `board-drift-20261112.json`, `packet-group-coverage-v6.json` + `delegations-20261112.json`, `archive-integrity-20261112.json`, `landing-gate-doc-check.json`. The landed text now says what is true: no guard modifies the GOVERNED state (manifest, plan, matrix, packets, archives, audio library), each refreshes its own receipt under `outputs/`, and the sweep adds one combined receipt. The item's own instruction to "state that the guards are read-only" was therefore wrong and was not followed.
     Records updated to the corrected commit: manifest 22,754 B sha256 `c6a3aa23a1cb0d29d6aeda8ae884cbd8aec361ca224a45f57245628cad482e49`; plan MD `d4ab0ea59894f1bc…` with "Already landed" now `c95da7ff22`; matrix provenance refreshed.
     Final sweep, all eight green together with the doc checker reading the LANDED doc: `CONSISTENT`, `AGREE`, `MATRIX_CONSISTENT`, `PLAN_TEACHES_LANDABLE_COMMANDS`, `BOARD_BOUND`, `COVERAGE_COMPLETE`, `ARCHIVES_INTACT`, `DOC_CLAIMS_MATCH_STATE`, rc=0, receipt `83fbc623…`.

55. [x] The sweep's per-guard verdicts are now verified against each guard's OWN receipt, and the checker is mutation-proven on five failure modes.
     `outputs/board-sweep-parse-check.py` 5,295 B sha256 `f7d22882404235cbd54777f589de5a46108c9e27b7585a11c07b61dabb9d83d9`. The guard->receipt map is explicit (no guessing), and the verdict resolver was derived from the receipts on disk rather than assuming a uniform shape: it tries `verdict`, then `status`, then `result` / `result.verdict`, and records WHICH field it used per row so a shape change shows up instead of silently passing.
     REAL RUN: 8/8 `MATCH`, verdict `SWEEP_REPORT_MATCHES_GUARDS`, rc=0, receipt `outputs/board-sweep-parse-check.json` sha256 `f45dd298a44c154d73e2462f22645c698f1479b14733698417088eb825236b4c`. All eight receipts currently carry a top-level `verdict`, matching the strings the sweep recorded: `CONSISTENT`, `AGREE`, `MATRIX_CONSISTENT`, `PLAN_TEACHES_LANDABLE_COMMANDS`, `BOARD_BOUND`, `COVERAGE_COMPLETE`, `ARCHIVES_INTACT`, `DOC_CLAIMS_MATCH_STATE`.
     FAILURE MODES, each on its own copy, each rc=1 naming exactly one guard:
     - swapped verdict (copy of the sweep receipt, `board-drift` recorded as `BOARD_DRIFT`): `board-drift.py: sweep recorded 'BOARD_DRIFT' but its receipt says 'BOARD_BOUND' (field verdict)`.
     - missing receipt: `archive-integrity.py: receipt archive-integrity-20261112.json is missing at …`.
     - no verdict field (stripped from a copy of the receipt): `landing-gate-doc-check.py: receipt … carries no verdict field`.
     - unreadable receipt (truncated JSON): `verdict-unblock-matrix-check.py: receipt … is unreadable: Unterminated string starting at: line 1 column 13`.
     - unknown guard appended to a copy of the sweep receipt: `unknown guard 'made-up-guard.py': no receipt mapping (add it rather than guessing)` — the map must be extended, never inferred.
     Positive control: pristine copies -> `SWEEP_REPORT_MATCHES_GUARDS`, rc=0, `problems: none`.
     Harness error recorded, not hidden: the first mutation round reused ONE copy, so M1's swap corrupted the fixture for the missing/verdict-less cases AND made the "clean" positive control report MISMATCH -- a false failure caused by my sequencing, not by the checker. Redone with four independent copy sets (A/B/C/P) plus a fifth for the malformed case; only then were the results above obtained. Real sweep receipt untouched throughout: `83fbc6230b972a2530e3787690314419d8265b0ef8d53328ad51fdb1ac0548cc`.

56. [x] Every group's actual landing refusal is now recorded in ONE artifact, and the "silently landable" detector is mutation-proven.
     `outputs/landing-refusals.py` 5,103 B sha256 `996028d4090e96c50db911c75ca1f02c9ff3f7e0ea9efc6e6e2cbc2430a0d329`; real receipt `outputs/landing-refusals-20261112.json` sha256 `e27a6508e5835776ac3594ea733e8d50231ebd063bee2c61dc41ee2ae92d7b94`, verdict `LANDING_REFUSALS_RECORDED`, rc=0.
     Per-group refusal, all **8/8 rc=3** (the expected refusal, none silently landable):
     - B4 blocking=4, A7 blocking=4, T1 blocking=6, T1b blocking=3, EL blocking=5, render_service blocking=1, LP blocking=1, GUARDS-WAVGUARD blocking=1 — each with the gate's own text, `CHECK REFUSED <group>: N file(s) have no PASS verdict`.
     **The item's premise was stale and is corrected here:** the manifest has **25** blocking rows, not 24 (`tests/test_prove8.py` joined the A7 group after that count was written; `scripts/sfx_policy.py` left it by landing). Sum of per-group blocking = 25 = the manifest's blocking rows, with **no blocking row outside a group** and no path claimed by two groups, so the counts are not double-counted folklore.
     Cross-checks the script enforces (any failure -> `LANDING_STATE_MISMATCH`, rc=1): a still-blocking group must not be landable; a zero-blocking group must not refuse; per-group sum must equal the manifest blocking total; no blocking row may sit outside every group; no path may belong to two groups; the matrix's group set must equal the plan's labels.
     Checker bug found and fixed on the first real run, recorded rather than papered over: the script compared raw plan keys (`"A7 (Packet A pass 7 PASS unblocks)"`) to the matrix's bare labels (`"A7"`) and reported a false mismatch. It now normalizes with `g.split(" (")[0]`; the post-fix run is the green one above.
     Mutation control: a throwaway manifest copy with create `render_service` flipped to a hash-bound PASS (fake packet containing the row's current sha256 `acb0a534…` plus `VERDICT render_service.py: PASS`) -> that group reported **rc=0 with 1 blocking row**, the script exited **rc=1** with `render_service (its own packet PASS unblocks): SILENTLY LANDABLE — rc=0 with 1 blocking row(s)`, `silently_landable: ['render_service …']`, groups-with-rc=3 dropped 8/8 -> 7/8. Real manifest and real refusal receipt were untouched by the mutation (both sha-verified unchanged).

57. [x] The refusal guard is now the NINTH sweep guard, proven three ways, documented and landed.
     `outputs/board-sweep.sh` 2,039 B sha256 `8a1570fa223c347c81d79615393d4c787e5bd4706815380450a2dcf62cac6e2f` (adds `landing-refusals.py` to `GUARDS`).
     (1) GREEN, all nine PASS, measured wall time **0.93 s** — far under the one-minute target even though the refusal guard re-runs `landing-check.sh` eight times: `CONSISTENT`, `AGREE`, `MATRIX_CONSISTENT`, `PLAN_TEACHES_LANDABLE_COMMANDS`, `BOARD_BOUND`, `COVERAGE_COMPLETE`, `ARCHIVES_INTACT`, `DOC_CLAIMS_MATCH_STATE`, `LANDING_REFUSALS_RECORDED`; combined receipt `outputs/board-sweep-receipt.json` sha256 `003010de55b442ae05a3b4ef25867045c913763120b4776ee26ca54edf6e279e` (`verdict=BOARD_SWEEP_PASS`).
     (2) STUB MUTATION of the ninth guard only (throwaway copy of the sweep script, `landing-refusals.py` -> `/tmp/stub-fail.py`, which prints `VERDICT: STUB_FORCED_FAILURE` and exits 1): rc=1, line `FAIL /tmp/stub-fail.py rc=1 STUB_FORCED_FAILURE`, receipt `BOARD_SWEEP_FAIL` naming exactly that guard; the real sweep receipt was untouched (`003010de…` before and after).
     (3) PARSE-CHECK MAPPING extended in `outputs/board-sweep-parse-check.py` 5,356 B sha256 `e72681cdb1502d086e962ff11f1dd02a1a3bc6ee81b40e69adcb1a2629089372` (`"landing-refusals.py": "landing-refusals-20261112.json"`). With nine guards it reports 9/9 `MATCH` — including `landing-refusals.py receipt_verdict=LANDING_REFUSALS_RECORDED` — verdict `SWEEP_REPORT_MATCHES_GUARDS` rc=0, receipt `3665c781fd6cffc30c5f2d658eb021ae5f40c1609b44d209f2df779dcae93b0c`. No unmapped guard.
     DOC: `references/verification-evidence.md` now 12,721 B sha256 `f475f58f3ca3051bc16625c0c753de23ce48bd60637a9cbafc4565def1274957`, LANDED `4da8ea307ca4d766b419829a18e4227b8c862d81` (local == `git show origin/main:`). Table grew to nine rows (the new one states the refusal guard's contract: per-group rc=3, counts sum to the manifest, no blocking row outside a group, no group silently landable), "eight remembered invocations" -> "nine", the receipt list gained `landing-refusals-20261112.json`, and the section now cites the nine-guard receipt sha plus the measured **0.93 s wall** time.
     Records updated: manifest 22,744 B sha256 `a3402591609fc16200a14dcdfd8f09a93bfcfc1ae190d6ad87d71ba57ff47c97`; plan MD `416116b537d3deb7…` ("Already landed" -> `4da8ea307c`); matrix provenance refreshed. Post-landing sweep + parse-check both green (9/9 PASS, 9/9 MATCH).

58. [x] T1 + T1b FAIL triaged against CURRENT bytes, every REAL finding fixed with a mutation control, gates green, and ONE combined resubmission built + delegated.
     Response read in full: `/tmp/surf-cb-T1/response.md` sha256 `538158c025fede83c5ad61982cc361af153001cb029669d876fd4cce1b930cb0` (matches the reported `538158c025fede83…`). **Sentinel mismatch recorded:** `WEBGPT_DONE:20261112T190532Z:595410e8` occurs **0 times** in that file; the sha matches, so the file is what surf says, but the sentinel is not verifiable from this copy.
     **Triage of all 19 findings — 15 REAL (fixed), 4 ALREADY FIXED** (the packet carried older harness bytes): T1-06 (absent-`copied.wav` predicate gone; published-artifact hashes + pathname-read mutant), T1-07 (pace sourced ONLY from the plan, `delivery={"tone": None}`, PH-05), T1-09 (full ordered compare, PH-02), T1-11 (ordered gains must equal `[-24.0, 6.0]`, label normalized).
     Real fixes, each with the mutation that proves the test discriminates:
     - **T1-01** `test_packet_a7_reporting.py:30–59` — new `[SV-17 C]`: a protected inode appears at `--out` mid-publication (race count asserted), manifest must stay byte-identical; mutation `exists()`-then-write writer is shown to truncate it.
     - **T1-02** `:148,164–172` — new `[SP-16 C]`: EVERY original file must exist and be byte-identical (receipt included); mutation restores the WAV and drops the receipt → fails new predicate, passes the old WAV-only one.
     - **T1-03** `:19–24,86–100` — confounded `verdict != PASS` replaced by a paired policy ON/OFF control: same fixture, `content == CHECKED` when available, non-content gates identical, unavailability alone adds the policy failure.
     - **T1-04** `test_prove4.py:91–98` — real 7-byte partial writes over a 10,240-byte nonuniform payload with full-byte comparison; mutant performs ONE unchecked short write and truncates.
     - **T1-05** `:79–89` — status measured (message-string exit codes are nonzero failures); `SystemExit(0)`/`None` are SUCCESS; valid-destination control must publish; the OLD predicate is kept as executable mutations proving it accepted both.
     - **T1-08** `test_prove6.py:69–73` — both-populated case (chunks win over a nonempty answer) + answer-first mutant that fails it.
     - **T1-10** `test_prove7.py:55–74` — each option asserted as a flag/value PAIR; flagless vector keeping the values fails the predicate.
     - **T1-12** `narrator_sfx_batch.py:162–164` — manifest update holds `flock` across read-modify-write, commits via same-dir temp + fsync + `os.replace`.
     - **T1-13** `:77–88,178` — private staging, mp3 `O_EXCL`, ffmpeg targets the staged path, publication is `os.link` (atomic no-overwrite); planted symlink destination refused, sentinel intact.
     - **T1-14** `:77–78,156–164,177–180` — provenance sidecar binds bytes+voice+text+model; missing sidecar, wrong sha, and same-bytes-different-text each REFUSED.
     - **T1-15** `:108–124,169–180` — interior placement splits the WORDS so the tag sits between two non-empty fragments; single-word sentences raise. Plan states **96 clips, 48 interior** (was "~30-clip").
     - **T1-16** `:90,153–156,176–187` — typed outcomes; missing output in execute mode is FAILED, listed, and rc=1 (`DONE (executed WITH FAILURES)`).
     - **T1-17** `:28–30,132` — key from `ELEVENLABS_API_KEY` else an explicit 0600 file (mode checked) else a labelled error; no rc-file parsing. Four behaviours proven.
     - **T1-18** `sanity.sh:17,19–28` — every mandatory check goes through `run_check` with an explicit failure branch; `cmd && echo OK` is gone.
     - **T1-19** `:41–45` — negative control must show the expected unknown-voice error and runs against a dead port, so a dispatch attempt fails it; stderr no longer discarded.
     Executed, in this tree: `./tests/run.sh` **rc=0** — 32/32, 22/22, 7/7, 16/16, 25/25, 23/23; `./sanity.sh` **rc=0** (retained harnesses OK, negative control OK, live render OK); `/tmp/t1fix/prove_batch.py` **20/20** (the T1-12..17 behavioural harness, included in the packet).
     Current hashes: `test_packet_a7_reporting.py` 14,729 B `4eea8ac9…`; `test_prove4.py` 11,106 B `b22c8f72…`; `test_prove5.py` 4,445 B `35cd0d43…`; `test_prove6.py` 7,437 B `ef889860…`; `test_prove7.py` 8,711 B `7cc24c5d…`; `narrator_sfx_batch.py` 16,088 B `a8904863…`; `sanity.sh` 3,216 B `aca091a8…`; `tests/run.sh` 762 B `9fa3ae51…`; `tests/.gitignore` 66 B `cc8d40de…`.
     **Resubmission:** `/tmp/cb-T1-pass9.txt` 79,830 B sha256 `85e225675764ede45d7ee438e10d8ae087ed6bf57f1bb23888e2c25e0f652ae6`; independent binding check says `PACKET_BINDS_LIVE_BYTES` for all nine files; 0 `/home/` and 0 `/mnt/` literals (sources sanitized; live-file hashes retained). Delegated to surf via intercom with the triage table and the executed counts.
     Errors I made and recorded rather than smoothed over: (1) the first prove4 exit-status fix did `int()` on this codebase's message-string `SystemExit` codes and crashed the harness; (2) the first T1-04 mutation called the REAL write while `os.write` was patched, so the "unchecked write" truncated nothing and proved nothing — redone as one partial call ignoring its count; (3) the packet builder resolved relative paths against CWD and failed; (4) my delegation message said "14 REAL / 3 ALREADY FIXED" — the true counts are **15 / 4** (T1-11 is the fourth already-fixed finding). The correction is sent separately.
     No T1 or T1b row is bound; both still await a verdict. `test_prove8.py` remains in A7.

59. [x] Landing records re-pointed at the repaired T1 surface with NOTHING bound, and all nine sweep guards green.
     Manifest rows changed to the current hashes, each carrying `hash_changed_at`, `previous_sha256` and a `hash_change_note` instead of a silent overwrite; every one left `review_verdict="NOT REVIEWED (current artifact)"` with `review_packet` cleared:
     - `test_packet_a7_reporting.py` 14,729 B `ef8017e75c18…` -> `4eea8ac91fd08a06dc50b89e860bc3e27d59b4a6c0d711b24004f3ffd7c4313a`
     - `test_prove4.py` 11,106 B `b7aedacdaf80…` -> `b22c8f7217bcfbeacf5b5cc748dbe87c9f784a78b91b6687afc23c3e144cb290`
     - `test_prove6.py` 7,437 B `9772c6cc4272…` -> `ef889860245aa09abccf26d2325f9b27fd64e6e105d1f6560360419531eab8f1`
     - `test_prove7.py` 8,711 B `82708176a7c9…` -> `7cc24c5d5f0806ccb14234c0accdff9623e6ec78dfee82c02c0adc19716297c1`
     - `narrator_sfx_batch.py` 16,088 B `6e2bef1102ff…` -> `a8904863468ab7d51b7a66a9ae42b8a530301796ec708ba1c08f3fd28907a4ac`
     - `sanity.sh` 3,216 B `7f64a0785a8f…` -> `aca091a8d42d2add5da39f2885e90dcba69099e0798fca002f036564f3dcf8cb`
     `test_prove5.py` needed a second fix the sweep exposed: its bytes did NOT change, but its row still pointed at the superseded `cb-B4-pass2` packet, so its packet was cleared too and its citation now records that the bytes are unchanged while the verdict is awaited in `cb-T1-pass9`.
     Delegations: `/tmp/cb-T1-pass9.txt` registered (`exists`, sha256 `85e225675764ede45d7ee438e10d8ae087ed6bf57f1bb23888e2c25e0f652ae6`, 79,830 B) and all **9** T1/T1b paths now await it instead of the superseded packets (verified: awaiting→pass9 True for 9/9).
     Coverage v6 re-run: `COVERAGE_COMPLETE`, 25 blocking = 18 `AWAITING_DELEGATED_PACKET` + 7 `POLICY_BOUND`, `uncovered: []`; owed T1 `['cb-T1-pass9.txt']`, T1b `['cb-T1-pass9.txt','cb-T1b.txt']`.
     Two guards failed on the first sweep and both were REAL record gaps, not noise:
     - `landing-plan-vs-manifest.py` DRIFT — the plan (JSON **and** MD) still carried the pre-repair hashes. Updated 6 hashes in each.
     - `verdict-unblock-matrix-check.py` MATRIX_DRIFT — the matrix still required the superseded packets. T1 per-path now `AWAITING_VERDICT(t1-pass9)`, T1b's two changed files `AWAITING_VERDICT(t1b-pass9)`, and `.gitignore` deliberately keeps its `cb-T1b` content-identity binding (its own assignment was flattened by my first rewrite and the checker caught it); `needs_two_verdicts` is now `['A7','GUARDS-WAVGUARD']`; provenance refreshed.
     Third gap, also real: `landing-gate-doc-check.py` went red because rule 4 still described T1's superseded two-packet split. Fixed the DOC, not the checker's claim: `references/verification-evidence.md` 13,006 B sha256 `c5e5fcc89556a6b5da3e830bca8ebb273e3e53e05c0eef1489957319cf8fd32b`, **LANDED `670bd3cbeab5b1052deeb23055d2e4afac236503`** (local == `git show origin/main:`), rule 4 now states the pass-9 resubmission binds all six T1 files plus `tests/run.sh` and `tests/.gitignore`. The checker's own T1 assertion was updated to the new truth, and my checker had a regex bug of its own: renaming the heading to "needed" made `4\. \*\*Some groups need two verdicts` stop matching, so rule 4 read as empty and four checks failed spuriously — regex now `need(?:ed)?`, recorded rather than quietly patched.
     **Nothing bound.** Explicit check: all T1/T1b rows are `NOT REVIEWED (current artifact)` (plus `.gitignore` `NOT REQUIRED`), `review_packet=None` for all except the content-identity `.gitignore`; `BOUND_VERDICT_VIOLATIONS: none`.
     Final nine-guard sweep: **all PASS, rc=0** — CONSISTENT, AGREE, MATRIX_CONSISTENT, PLAN_TEACHES_LANDABLE_COMMANDS, BOARD_BOUND, COVERAGE_COMPLETE, ARCHIVES_INTACT, DOC_CLAIMS_MATCH_STATE, LANDING_REFUSALS_RECORDED; receipt `outputs/board-sweep-receipt.json` sha256 `003010de55b442ae05a3b4ef25867045c913763120b4776ee26ca54edf6e279e`.
     Current record hashes: manifest 24,814 B `cbb450a8ebd2…`; plan JSON `178b30b520e3…`; plan MD `8e73b2dbd3b7…`; delegations `36c670297c8a…`; coverage v6 `4db5010a193c…`; matrix `3de5272f8bdb…`; doc-check `fede82e620fe…`.

60. [x] First REAL verdict processed: A7 pass 8 reviewed, **PACKET VERDICT FAIL**, and the mechanical-record consequence recorded (nothing lands; repairs required).
     `outputs/verdict-watch.py` 6,202 B sha256 `8a64f2a489e51dc9f6cf66b79da3aa35d612fd688688b0832c66dc4372241e5c` matches each outstanding packet to its surf transport directory by the packet's OWN bound artifact hashes appearing in `prompt.md`, reads the transport receipt, and — when `response.md` exists — requires both a `VERDICT <file>: PASS|FAIL` line and the row's CURRENT sha256 before it will say `READY_PASS`. Receipt `outputs/verdict-watch.json` sha256 `3d5eb19f42cef2833d662bd379a8b899223b8de2c28b7f4b9f00e3f6f2f10ce1`, `ready_to_process: none`:
     - `cb-A7-pass8.txt` -> **PREPARED_NOT_SUBMITTED**, matched `/tmp/surf-cb-A8` (`transport_status=prepared_prompt`, `submitted_to_chatgpt=false`; heartbeat `phase=prompt_prepared`, `submitted_at=null`, updated `2026-11-12T19:28:10Z`). The prompt is staged; ChatGPT has not been given it.
     - `cb-T1-pass9.txt` -> **NO_SUBMISSION_FOUND** (no transport dir whose prompt contains its bound hashes).
     - `cb-wg-review.txt` -> **RESPONSE_UNBOUND**, matched `/tmp/surf-cb-A6` (response sha256 `593da29485fe18e568e250e6f8406267607354767ac901f8afa0076486f6cd67`). That response carries verdicts for `sfx_verify.py FAIL`, `sfx_policy.py PASS`, `spyke_render.py FAIL`, `interrupt_sfx.py FAIL` and **none for `wav_guard.py`**; `hash_unbound: ['wav_guard.py']`, `no_verdict_line: ['wav_guard.py']`. This is exactly the "hash in a packet is not a verdict" case, now machine-classified.
     Cross-check without the watcher's matching logic: grepping every `/tmp/surf-cb-*/response.md` for verdict lines naming the outstanding files returns only historical hits (`A4` `wav_guard FAIL`, `A5` `wav_guard PASS` — both bind older bytes, `T1` `sanity.sh FAIL` — already superseded by the pass-9 repairs). No response rules on the current surface.
     Therefore no verdict was fed to `verdict-intake.py`, no row was bound, and the mechanical path is untested against a REAL verdict this turn — testing it against a synthetic one would only re-prove item 49. It stays proven on copies (four refusal directions + one acceptance) and will run for real on the first `READY_PASS`.
     Watcher mutation-proven on three separate fixture roots: a response with `VERDICT wav_guard.py: PASS` + the current sha -> `READY_PASS`; the same PASS without the sha -> `RESPONSE_UNBOUND` with `hash_unbound: ['wav_guard.py']`; `FAIL` + sha -> `READY_FAIL`. First fixture round reported NO_SUBMISSION_FOUND for ALL cases and that was a watcher defect, not a fixture flaw: the matcher demanded >=2 hash hits while `cb-wg-review.txt` binds exactly one, so no single-hash packet could ever match. Bar is now `min(2, len(hashes))` with `hits > 0`; all three cases then classified as intended.

     UPDATE (same day, HOLD turn): **a REAL verdict now exists and the watcher cannot see it.** Surf split the A8 packet into halves: `/tmp/surf-cb-A8a` (prompt 76,398 B, three files) returned `submitted_to_chatgpt: true` and a 16,664 B response sha256 `5690bde9a853db35de55a7bf1347fc46195303e4dc1b18afc34f880fd8d19599` whose first line is `Packet A pass 8, half 1: FAIL` (receipt `e34a09b96c6f35e0…`, sentinel `<<<WEBGPT_DONE:20261112T202310Z:6a20ed54>>>`); `/tmp/surf-cb-A8b` is `submitted` / `waiting_for_acceptance` (updated `2026-11-12T20:47:00Z`). **Neither prompt contains the A7 packet sha `68d744b1…`** (grep count 0 in both), so `verdict-watch.py` still reports `PREPARED_NOT_SUBMITTED`/`none` and `submission-freeze.py` cannot bind the halves either. Consequence: the hold's trigger did NOT fire, no intake was attempted, and a verdict is sitting on disk that the gate is blind to — recorded as a binding defect, not routed around.

     VERDICT BINDING (the reason item 60's watcher never saw it): surf delivered `cb-A7-pass8.txt` (`68d744b1…`) as TWO byte-exact halves, each carrying the full preamble, because the 135 KB prompt exceeded the 128 KB single-argument limit (`setsid: Argument list too long`).
     - half 1 `/tmp/cb-A8a.txt` 74,856 B sha256 `b0a43e74b6d7d7fa029bedb89f861abc0e0be105f993087cd99ed396510c5998` -> `/tmp/surf-cb-A8a/response.md` 16,664 B sha256 `5690bde9a853db35de55a7bf1347fc46195303e4dc1b18afc34f880fd8d19599`, first line `Packet A pass 8, half 1: FAIL`, sentinel `WEBGPT_DONE:20261112T202310Z:6a20ed54`.
     - half 2 `/tmp/cb-A8b.txt` 64,323 B sha256 `52a8bcc55469b2a040c00f569a807db6857f71d14e7d46669a9bde4377a83041` -> `/tmp/surf-cb-A8b/response.md` 15,690 B sha256 `fabde15f08dfef6031529ac019bd0962d5c1c2261874057e59b78d9a98428386`, first line `## HALF 2: FAIL`, sentinel `WEBGPT_DONE:20261112T203740Z:f6aaa6c1`.
     - INDEPENDENT content check (not surf's claim alone): all **2,901/2,901** original lines of `cb-A7-pass8.txt` appear in one of the two halves; the size excess (139,179 vs 133,984) is the duplicated preamble.
     - Why the guard was blind: neither half contains the A7 packet sha `68d744b1…`, so `verdict-watch.py` kept reporting `PREPARED_NOT_SUBMITTED`/`ready_to_process: none` even after both responses existed. That is a REAL binding defect, queued as item 69.
     VERDICTS: `sfx_policy.py` **PASS** (bound to `5c3d2ce62a1034850df60f48b184afa57361fb5d3212875f55a1e0d133ab293a`); `sfx_verify.py` **FAIL**; `tests/test_prove8.py` **FAIL**; `spyke_render.py` **FAIL**; `interrupt_sfx.py` **FAIL**; `PACKET VERDICT: FAIL`.
     MECHANICAL CONSEQUENCE, applied honestly: a FAIL is not intake-able and nothing lands. The manifest rows stay blocking. Known imprecision recorded rather than papered over: those five rows still read `NOT REVIEWED (current artifact)` although the current bytes WERE reviewed and failed; modelling FAIL as a first-class row state is queued with item 69, not hand-edited now.
     Cross-correction received from surf: the `WEBGPT_DONE:…595410e8` sentinel for T1 IS real — it lives in `response.md.raw.md` and `response.md.submitted.md`, and `extract` strips it from the cleaned `response.md`. My "absent from the file" observation was true of the cleaned file only; recorded as resolved.

61. [x] Submission surface FROZEN and the freeze is now a command: real run `ALL_FROZEN`, mutation flags exactly one file, nothing bound touched.
     `outputs/submission-freeze.py` 6,393 B sha256 `849d1f2ce07f22e5248d872a655a4116ddafa043422639be4825a37b25010bf2`. Real run **ALL_FROZEN** rc=0, receipt `submission-freeze.json` sha256 `d6f12dc7e608c931…`: A7 pass-8 5 bound FROZEN, T1 pass-9 9 bound FROZEN, wg 1 FROZEN; prose mentions reported `MENTIONED_NOT_BOUND`.
     Mutation on `/tmp/freeze-mut` (15 copied files): appending one byte to the COPY of `sanity.sh` flagged exactly `('sanity.sh','DRIFTED')`, overall DRIFT, rc=1; restore -> ALL_FROZEN rc=0; the real files were never touched.
     Three self-caught checker defects recorded: mentions counted as bindings; a self-contradictory `ALL_FROZEN` beside per-packet DRIFTED; `MANIFEST_DRIFT` masking `DRIFTED` (drift now takes precedence, manifest disagreement secondary).

62. [x] Freeze became continuous: tenth sweep guard, proven able to fail the sweep by name, no packet-bound file touched.
     `outputs/board-sweep.sh` 2,062 B sha256 `2a33b92a9057ccb7e905761f9329b5aad1cdb4a16d220bffec54ca4c97e43307` (adds `submission-freeze.py` as guard 10). Ten-guard green, measured **0.96 s wall**, receipt `board-sweep-receipt.json` sha256 `f3d977c5442e0f1a7f457dcf03413be28d035d90384bfa2584a366776ccfa59f`.
     Parse-check extended (`"submission-freeze.py": "submission-freeze.json"`; 5,410 B sha256 `35aeaa2f8fa6f64288e6f6a085279ebefc397e6d66e459603e822c25931ae5c4`), **10/10 MATCH**, receipt `c13ec269771b9a8ee9866f16ddecc79fee61b907c8ba9ed3c22db3859c462053`.
     Tenth-guard stub mutation -> `FAIL /tmp/stub-fail.py rc=1 STUB_FORCED_FAILURE`, `BOARD_SWEEP_FAIL` rc=1 naming it; the real receipt stayed `f3d977c5…`.
     Doc `references/verification-evidence.md` 13,300 B sha256 `b75efe0c20f18aa3ed1b411a14a84ff7fa25588304239d3ee2bcd07d9bccd42c`, **LANDED `63a8a8fad2b3400ba9e8c49ce2c9283244ed8ab3`** (local == origin blob). Records: manifest `164c76f8df08…`, plan MD `0cb848cd…`, matrix `239b5a8e…`. Post-landing sweep green; freeze **ALL_FROZEN** receipt `50d7f953…`.

63. [x] Harness->module identities RECORDED (additive, no harness edited), both mutation directions proven, frozen tree untouched.
     `outputs/harness-module-identities.py` 6,598 B sha256 `f5557a897a3af4a5e715451971330741d664ea2b421c395fa932c96c584367ee`; parses each harness's AST imports (six production modules), records live sha256/bytes, harness sha/bytes and executed check counts, then re-hashes every recorded module independently.
     Real run **IDENTITIES_BOUND** rc=0, receipt 5,200 B sha256 `2081cc54b5e7537e56ea1a3cf26114d83e5cbb60272aa050f7730a7a452cce6b`, 6 harnesses / **15 module hashes verified live** (`live_hash_mismatches: []`): a7_reporting 32/32 (`interrupt_sfx@4911df2f`, `sfx_verify@b35fa49a`, `spyke_render@97cef036`); prove4 22/22 and prove5 7/7, prove6 16/16, prove7 25/25 (`arc_chart@17ccab9c`, `speak@7c238086`, `speak_core@34274405`); prove8 23/23 (`sfx_verify@b35fa49a`, `spyke_render@97cef036`).
     Mutation, copy direction: `speak_core.py` +1 byte in a copied tree -> `IDENTITIES_DRIFT` rc=1, four entries (`prove4/5/6/7:speak_core` `342744057172…` -> `6f2e9555ac95…`), receipt `a5cd6e6a…`. Reverse (stale record vs real tree) -> rc=1, `stale-record=6f2e9555 live=342744057172` x4, receipt `bb63cf4c…`. Positive control `952e99d8…`. Real record unchanged; freeze `ALL_FROZEN`.

64. [x] Identity check became the eleventh sweep guard with a no-self-heal policy.
     `outputs/board-sweep.sh` 2,093 B sha256 `e3f1ba7acd86efe6bfea2d0d7a860c8e558aa92a5089b7e0a7bf753e330d016c`; checker has `--record` (human) and guard mode. On drift it **never rewrites the record**: rc=1, `baseline_rewritten: false`, drift receipt `74798c544317fe39…`, baseline byte-identical before/after (`2081cc54…`).
     Eleven-guard green, **1.07 s wall**, receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e`; guard receipt `harness-module-identities-guard.json` sha256 `01b0256afa05fc6669de2906497a417ec3bb9e3307118e57f08f254ebc8a5ee8`. Stub mutation of guard 11 -> `BOARD_SWEEP_FAIL` rc=1 naming `/tmp/stub-fail.py`; real receipts untouched.
     Parse-check 5,486 B sha256 `43f3bd9bfe55d604de4e074711c6cb93b76ade4046eca68568cdbcf6207237e7`, **11/11 MATCH**, receipt `2f3b624c273c5e7a11b3240a161416a02fc9befb553e23e1213c62b802cb16c9`.
     Doc 13,893 B sha256 `5b5b7e10f2fb33201a75e4d12e718ed1e683a563329dee1be82ae5a5827e1d3a`, **LANDED `245a52d7b3e7118aa4868ce37557f983822fd0d3`**; manifest `372bf76d…`, plan `1b235848…`, matrix `0568d78f…`; ALL_FROZEN `ae5dfccc…`.

65. [x] Freeze DERIVES its packet set, covers `cb-B4-pass2.txt`, reports exclusions, and the B4 mutation flags exactly one file.
     `outputs/submission-freeze.py` final 8,556 B sha256 `75d5db59361cf80aacb092ba32ccc9b9202b86ddfefeb07c114ff72a8bf8a22c`; hardcoded list gone. Derivation = `delegations.awaiting` targets ∪ PENDING manifest rows' `review_packet` ∪ explicit `--packet`, each recorded with its source and the files it governs.
     Discovery: `cb-A7-pass8.txt` (awaiting; governs interrupt_sfx/sfx_verify/spyke_render/test_prove8), `cb-B4-pass2.txt` (pending manifest row; governs **arc_chart/speak/speak_core/test_core_contract**), `cb-T1-pass9.txt` (awaiting; governs 9 paths), `cb-wg-review.txt` (awaiting; governs wav_guard). Exclusions recorded, not silent: `cb-A6a.txt` (LANDED `1d368faed3`), `cb-T1b.txt` (NOT REQUIRED).
     Real run **ALL_FROZEN** rc=0, receipt sha256 `66968cfc0106d0eb2124223dd1c6c5d26f9965ccba736fc66d57d424865e3906`: B4 governed=4 **all four FROZEN**; A7 4 FROZEN (+2 mentions); T1 9 FROZEN (+3 mentions); wg 1 FROZEN.
     Governance explained: files are checked against the packet that GOVERNS them; B4's stale mentions of run.sh/sanity.sh/prove4/6/7 (changed by the T1 repairs) are `SUPERSEDED_REFERENCE` (5, informational), not failures.
     Mutation (copies, `--out` redirected): unmutated control `ALL_FROZEN` rc=0 (`0c9dbb40…`); `speak_core.py` +1 byte -> rc=1 `DRIFT`, exactly `('cb-B4-pass2.txt','scripts/speak_core.py','DRIFTED')` `claimed=342744057172… actual=6f2e9555ac95…`; real tree untouched. Sweep receipt stayed `f50bac12…` (verdicts only), freeze receipt changed as predicted; parse-check 11/11.

66. [x] Doc aligned with the freeze code, landed, and guard expansion HELD.
     `references/verification-evidence.md` 14,714 B sha256 `2faec8e02e7c89016eef13930a110e34d8693e50d646342f34847fcadc5ef030`, **LANDED `338549ac973afd6488e92cabf2ce1217c85f86b2`** (blob verified). Freeze row now states: packet set derived (sources recorded), completed references excluded with reason, files checked against their governing packet so stale mentions are `SUPERSEDED_REFERENCE`.
     Records: manifest `f7754e9f…`, plan MD `1435b161…`, matrix `d1beb4e0…`. Sweep green; sweep receipt unchanged `f50bac12…`; freeze receipt changed to `c8851eca…`; parse-check 11/11. Hold respected: no new guard, no bound file touched.

67. [x] HOLD exited on its stated trigger: the A7 pass-8 response exists, is verified against the packet content, and is a FAIL.
     EXIT EVIDENCE: surf's message (seq 114) states the split and verdict; both response files and their sha256s are recorded under item 60; the 2,901/2,901 line-containment check was performed here, not taken on trust. During the hold: no twelfth guard, no new checker, no new record type, no packet-bound file modified, only read-only status checks (`verdict-watch.py` receipt `96a1767f…`).
     COORDINATION DELIVERED: surf received the T1 triage correction (**15 REAL / 4 ALREADY FIXED**, T1-11 being the fourth) and the sentinel observation, which surf has now resolved (raw/submitted files, stripped by `extract`).

68. [x] A7 pass-8 FAIL fully repaired: every confirmed-real finding fixed with an executed mutation control, gates green, and ONE packet that binds the group delegated to surf.

     FIXES (production), each verified against the current source and proven with a control that fails on the old code:
     - **SV-23** `sfx_verify.py` close() error preserved; publication SKIPPED when close was the first failure; first error wins; no retry of a closed fd. Control: injected post-close `OSError(EIO)` -> diagnostic returned AND destination absent; clean write still publishes; publish-once still refuses. New sha256 `049b11c6e035c1c7…`.
     - **SV-24** manifest read is now `_read_manifest()`: ONE open with `O_NONBLOCK|O_NOFOLLOW`, `fstat` regular-file check, documented `MAX_MANIFEST_BYTES` (8 MiB), bounded read on that descriptor. Controls: FIFO manifest rc=2 in 0.28 s with a structured report; oversized manifest rc=2 in 0.31 s; normal manifest still parsed.
     - **SV-25** whole `TemporaryDirectory` lifecycle inside the conversion scope; `KeyboardInterrupt`/`SystemExit` still propagate. Controls: injected creation ENOSPC and cleanup EIO both become `AsrResult(ok=False, error=…)`; cancellation still propagates.
     - **IS-20** `interrupt_sfx._manifest_references()` now RAISES on unreadable/invalid manifest instead of returning False, so the caller's `unresolved` branch keeps the committed clip. Controls: committed True; absent False; invalid JSON raises; invalid structure raises; unreadable (chmod 000) does NOT return False. New sha `8291537eb31af27a…`.
     - **IS-21** empty-ASR selftest now writes a REAL AC WAV fixture (0.6 s 220 Hz sine), uses `AsrResult(ok=True, transcript="")` (the actual field), asserts the stub was REACHED and `ok is True`, and requires the advisory wording. `selftest()` -> 0 problems.
     - **SP-18** rollback no longer does stat-then-unlink: `_discard_if_ours()` renames the name aside atomically, inspects the moved inode, deletes only its own, and restores foreign bytes with a no-clobber link (parking + reporting if the destination was re-created). Controls: own inode removed; foreign inode NOT deleted and its bytes unchanged; no tombstone left. New sha `488a3acb309326b3…`.
     - **SP-19** `_overwrite_message()` no longer OPENS prior receipts (names only). Control: existing WAV + FIFO receipt -> `FileExistsError` in 0.00 s.
     - **POL-04** `words()` retains Unicode lexical tokens; and my own control caught a SECOND real defect while fixing it: the final fall-through accepted ANY multi-token transcript without function words as "interjection / non-lexical", so a French sentence passed. It is now advisory (`multi-token transcript, not a recognised vocalisation`). Controls: `Ceci est une phrase ordinaire` -> advisory; `ha ha ha ha` -> accept; `mm-hm mm-hm` -> accept.
     - **POL-05** `selftest()` now exercises `classify_content()` with a sentence, a non-ASCII sentence, a repetition and a cue; a mutant that makes it always-accept produces 2 selftest failures (previously undetected). New sfx_policy sha `c3c9e92ae5d66940…`.

     HARNESS FIXES `tests/test_prove8.py` (new sha `cc5d77b553d54927…`), now **31/31** with 9 new oracle checks:
     - **A8-PROOF-01** both renderer "mutation controls" now EXECUTE real source-copy mutants: deleting `backups.append(...)` loses an original under the same interrupt; deleting `created.append(...)` leaves an untracked WAV. First version of the second control measured a completed render because `allow_overwrite=True` publishes via `os.replace` (the link interrupt never fired) — corrected to publish through `os.link` on a fresh name; recorded.
     - **A8-PROOF-02** genuine AC fixture (sine, not DC); identical bytes are **PASS with policy and FAIL without**; a mutant that hides policy-unavailability fails the oracle.
     - **A8-PROOF-03** rollback ownership at the post-publication boundary: a foreign inode installed at the published name survives; a mutant that removes the inode comparison DELETES it (proving the guard is load-bearing).
     - **A8-PROOF-04** digest-verified REUSE surfaces the retained advisory and its reason; a mutant that removes the branch is caught.
     - **A8-PROOF-05** the receipt records the harness sha256/bytes, the four loaded-module sha256/bytes, and the runtime version.
     - **A8-PROOF-06** the refused existing output is compared by FULL hash before/after; the FIFO output case runs in a bounded child (rc=2, no hang).

     GATES: `./tests/run.sh` rc=0 — 32/32, 22/22, 7/7, 16/16, 25/25, 31/31; `./sanity.sh` rc=0 (retained harnesses OK, negative control OK, live render OK).

     PACKET: `/tmp/cb-A7-pass9.txt` 150,564 B sha256 `a2a17a6e95cb82d6a4d7c945e6e0ff8a70060f8154b3fbf4125edd7801ffff65`, binds all five files (independently re-checked: `PACKET_BINDS_LIVE_BYTES: True`). It carries 4 `/mnt/...` literals because they are real module constants (manifest path, artifacts root, library dir); tokenizing them would break the byte-exactness the declared sha promises, so they were kept and disclosed. **Delegated to surf** with the >100 KB attachment rule, requesting `VERDICT <file>: PASS|FAIL` per file against those hashes.

     RECORDS brought into line with the new bytes (the model, not just the prose): manifest `b337f5aff8de…` (five rows re-opened to `NOT REVIEWED (current artifact)` with `previous_sha256`/`hash_change_note`, `sfx_policy.py` un-landed because its bytes changed); plan JSON A7 grows to **five paths on pass 9**, plan MD table+command updated; matrix A7 `AWAITING_VERDICT(a7-pass9)` with pass-9 packet entry; coverage `COVERAGE_COMPLETE` (26 blocking: 14 awaiting + 5 A7 delegated + 7 policy-bound); delegations keyed by the row paths AND with the packets entry `exists: true` (coverage looks up the full path); identities baseline **re-recorded deliberately** (`--record`, receipt `eba6923a…`) because this was the intended change; doc rule 4 rewritten to pass-9 and **LANDED `50008142fe1175bfb675fa1c39bef49f853297ff`** (sha `146f88f9e809…`, local == origin). `landing-gate-doc-check.py` updated to the pass-9 claim it must verify (packet path/sha, five paths, matrix need).
     VERIFICATION: **eleven-guard sweep PASS (11/11, rc=0)**, receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e`; `submission-freeze.py` **ALL_FROZEN** (receipt `3d90dfd4…`: pass-9 governed=5 all FROZEN, B4 4, T1 9, wg 1); `harness-module-identities.py` **IDENTITIES_BOUND**.
     SELF-CAUGHT DEFECTS, recorded not hidden: three of my own probe assertions were wrong (errno names not in messages; an empty-but-valid manifest reports "no clips selected" rather than writing a report); the POL-04 fall-through above; the mut2 control publishing via `os.replace`; delegations keys mixed basename vs repo-relative path; and my doc citation used an 8-hex prefix where the guard requires ≥12.


69. [x] Binding defect CLOSED: verdicts are matched by the CONTENT they review, a FAIL is a first-class row state, and both are mutation-proven.

     WATCHER `verdict-watch.py` (9,295 B sha `3a6fbafb4288245dec611f07da2c4875aefd343cad7e9ca026fb5a1232598768`). Four real defects, each of which alone hid the A8 halves:
     1. Only `prompt.md` was read, so an ATTACHED packet (A8b's `cb-A8b-packet.md` under a 1.5 KB prompt) was invisible. Now `transported_hashes()` reads prompt, submitted prompt and attachments, and deliberately EXCLUDES `response.*` so the answer cannot match itself.
     2. Tie-break `sorted(..., key=(hits,-mtime))[-1]` selected the OLDEST dir on equal hits - exactly the stale `/tmp/surf-cb-A8` instead of the live halves. Now highest hits, then newest.
     3. Only per-file `VERDICT <file>: PASS|FAIL` lines were parsed, so a packet-level FAIL ("Packet A pass 8, half 1: FAIL", "## HALF 2: FAIL") was invisible. Now `PACKET_FAIL`/`PACKET_PASS` are recognized.
     4. Only the newest matched dir was evaluated, so a split was never judged as a whole. Now every matched dir is evaluated and the group is `READY_FAIL` if ANY half fails, `READY_PASS` only if every half passes.
     FIXTURE PROOF (`/tmp/w69`, split-half pair + other-group control): OLD watcher -> `RESPONSE_UNBOUND`, `ready_to_process: none` (the bug); FIXED watcher -> `READY_FAIL`, `matched_dirs=[surf-cb-h2, surf-cb-h1]`, `attempts=[(h2,READY_FAIL),(h1,READY_FAIL)]`; CONTROL: a transport dir carrying ONLY other-group (`speak_core/speak/arc_chart/test_core_contract`) hashes is never matched for A7.
     REAL RUN (receipt `verdict-watch.json` sha `006294b739e3d8a016a2a8555b887c482f14cf203d07dadccd42fd5ce6d2d06e`): `{NO_SUBMISSION_FOUND: 1, SUBMITTED_NO_RESPONSE: 1 (cb-T1-pass9 at /tmp/surf-cb-T9), READY_FAIL: 1 (cb-wg-review)}`.

     FAIL AS A FIRST-CLASS ROW STATE (this is the decided representation):
     - `verdict-intake.py` rewritten: PASS and FAIL both require the file's CURRENT sha256; `review_verdict="FAIL (<report>)"`, `review_citation` quotes the FAIL line, `reviewed_sha256` records the exact bytes that failed, `review_state="FAILED"`, `landable_now=false`, `landing_commit=null`. PASS and FAIL are applied ATOMICALLY on a copy, and with any FAIL present the landing gate MUST refuse the group (rc!=0); a gate that accepted it is itself the defect. Unmentioned/outside-group/hash-unbound/contradictory still refuses the whole intake.
     - `packet-group-coverage-v6.py` (5,540 B sha `395a53c7587dcc10eccb098b22605951d3a0fb13072598ca1a09f117af666f6d`): `REVIEWED_FAIL` is a RECOGNIZED blocking state **only at the bytes it reviewed**; a FAIL recorded for other bytes becomes `UNCOVERED` ("re-review is required"). My first patch was dead because a following standalone `if review_binding ... else` overwrote `state`; the fix was an `elif` chain - recorded, not quietly corrected.
     - `verdict-unblock-matrix-check.py` (4,498 B sha `90daf5b8e204da4dbfdc72e993ac882e06024e18b056acbf842cec74435dd3c7`): accepts `FAIL_REPAIR_REQUIRED` only while the row records FAIL at its CURRENT bytes, else it reports matrix drift / re-review required.
     COPY PROOF on a full mirror of `outputs/` (real artifacts untouched): a complete five-file report with 1 FAIL + 4 PASS applied as `4 PASS, 1 FAIL`; landing-check refused the group as required; coverage `COVERAGE_COMPLETE` with `counts={'AWAITING_DELEGATED_PACKET':14,'BOUND_WITH_VERDICT':4,'POLICY_BOUND':7,'REVIEWED_FAIL':1}`, blocking=26; matrix `MATRIX_CONSISTENT`; refusals record A7 blocking=5, total 26, 8/8 rc=3. MUTATION CONTROL: setting `reviewed_sha256` to `0…0` flips coverage to `UNCOVERED` ("FAIL recorded for 000000000000 but the row is 049b11c6e035") and matrix to `MATRIX_DRIFT`; reverting restores both. Real manifest `b337f5aff8de…`, matrix `1f0a4d75…` and coverage receipt `4e20e407…` were unchanged throughout.
     SWEEP: eleven guards PASS (rc=0), receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e` (unchanged, as it records verdicts only); parse-check `SWEEP_REPORT_MATCHES_GUARDS` 11/11, receipt `2f3b624c…`.

     SPLIT-HALF POLICY settled with the evidence, no registration needed: content matching binds byte-exact halves, and surf's standard is now ONE attached `.md` for packets over ~100 KB (A7 pass 9 was delegated that way). Registration is therefore a fallback, not the mechanism.

70. [x] T1 pass-9 FAIL processed: the three reproduced production defects and the batch-proof hole are FIXED and mutation-proven; the harness mutation-control rewrite (T1-20) and T1-03/T1-06 remain, so this item is NOT closed.

     PRODUCTION `scripts/narrator_sfx_batch.py` (18,695 B sha `2c385c5f51ca5abe76537b0e496873a7d6fd8cea8b9102a275b9e13796d19831`):
     - **T1-22** provenance facts now come from the PRIVATE staged artifact before publication (`digest`/`duration` captured, sidecar written from them), and the published inode is re-read through an `O_NOFOLLOW` descriptor and compared to the staged digest; a mismatch returns `failed` and writes NO provenance. Proof `/tmp/t1fix/prove_fixes.py`: with a hook that atomically replaces the destination after publication, `tts` returns `failed` ("changed between publication and provenance") and the provenance file is absent; the positive control publishes and its sidecar digest equals the published bytes.
     - **T1-23** `record()` now reconciles `existing_verified` too: `_manifest_update(..., ensure=True)` validates an existing record and CREATES a missing one; a conflicting record raises and is counted as a failure. Proof: after deleting the manifest, an ensure call recreates the entry; a record with a different sha raises; an exact record is accepted.
     - **T1-24** `_ensure_meta()` replaces the `except FileExistsError: pass`: an existing sidecar is READ and its sha256/voice/placement/text/take compared; a conflict raises and fails the clip; a missing sidecar is created.
     - **T1-25** metadata is written through the `mkstemp` descriptor (`os.fdopen(fd, "w")`, flush+fsync) and the temporary path is removed in `finally`; 6 creations leave the fd count unchanged.
     MUTANTS (proofs must catch reverted code): removing the post-publication verification makes the replacement test return `generated` (defect reproduced); removing metadata validation lets a wrong-sha sidecar pass. Both caught. `/tmp/t1fix/prove_fixes.py` ALL PASS, sha `7d3506040d96cfa9bedebcfd1ef0697ba4cf466215ff187073908b5de27f9e5e`.

     BATCH PROOF `/tmp/t1fix/prove_batch.py` (**27/27**, sha `9e7682f689dc37ed683510e2d8a6d925e45d216c33522fd444e265c3381b0cac`): added a **success publication control** (clean destination publishes, bytes equal the staged bytes, staged inode survives), an **always-refusing production mutant** loaded from a disposable source copy whose `_publish_no_replace` raises - the success control is proven to CATCH it (`mut_ok is False`), which is exactly the mutation the reviewer used to get 20/20 on broken publication; **real `tts` missing-output** (ffmpeg stubbed to succeed and write nothing, ffprobe runs for real -> `failed`); and `_manifest_update` is now actually exercised (entry written; conflicting sha refused), so the claimed T1-12 coverage is no longer unsupported.

     SANITY `sanity.sh` (3,575 B sha `82b388e5e62cf5dc6b5838b42e6bdf375440f4019bb4c969d2551688fac7d0a0`) - **T1-19 fixed**: the negative control now requires the LOCAL VALIDATION text (`unknown voice`), case-insensitively, and rejects any transport symptom (`timed out`/`timeout`/`connection`/`refused`/`unreachable`). The reviewer's failing input (`RuntimeError: render timed out for voice nosuchvoice`) is now a FAIL. `./sanity.sh` rc=0, "negative control OK", live render OK. Local-path literals removed for live-hash binding: `./run.sh` replaced with `"$SCRIPT_DIR/run.sh"` and no `/tmp` paths remain, so a re-sent `sanity.sh` can bind the live bytes.

     GATES on the current tree: `./tests/run.sh` rc=0 - 32/32, 22/22, 7/7, 16/16, 25/25, 31/31; `./sanity.sh` rc=0. The retained harnesses are unchanged in this step; their mutation-control rewrite is the remaining work.

     REMAINING (blocking closure, queued as 71): **T1-20** the ten cited "mutation controls" still execute fabricated values / test-only helpers instead of mutated production code (test_packet_a7_reporting.py:86,93,243,248,251; test_prove4.py:106,114,118,155,242; test_prove6.py:79,82; test_prove7.py:45,47,48,98,100,137). **T1-03** assert the available/unavailable verdicts in test_packet_a7_reporting.py:145-153. **T1-06** run the REAL renderer under the forced swap and inspect the artifacts it produced (test_prove4.py:204,225,232). Then one attached packet binding the current hashes, delegated to surf, and the mechanical intake/sweep path.

71. [x] Remaining T1 pass-9 findings closed with EXECUTED PRODUCTION MUTANTS, and one packet re-delegated.

     NEW RETAINED HARNESS `tests/test_t1_20_mutation_controls.py` (7,916 B sha `30d252cf50d96707fa46f5a5ed628537ff6d28fcb48cd3cc806fc0e5a18579fb`) + `tests/mutant_support.py` (1,121 B sha `2292349f16308b23adc7946d498da167a129828bf49d34bfa0962324e7e039b4`): `load_mutant()` copies a production module, asserts each injected anchor occurs exactly once, imports the copy, and the harness runs the SAME behavioral assertion against production and mutant - PASS on production, CAUGHT on the mutant. Result **11/11**:
     - **T1-20a** transcript: production `_caller_plan_transcript` returns the chunks ("one two"); the answer-first mutant returns "SPOKEN ANSWER" (the both-populated case).
     - **T1-20b** short writes: production `arc_chart._write_all` lands all 10,240 bytes under a 7-byte `os.write`; the single-write mutant truncates to 7.
     - **T1-20c** report install: production `sfx_verify._write_report` refuses an ALIASED destination and the manifest stays byte-identical; the open-and-write-over mutant truncates the manifest (changed=True).
     - **T1-03** verdicts asserted: policy-unavailable -> `FAIL` (not PASS); available -> `PASS`; a forced-PASS verdict mutant is caught.
     - **T1-06** the REAL `speak_core.render` runs under the forced swap: it refuses and its OWN output dir holds 0 artifacts, none carrying the outside bytes. No mutant claim is made here on purpose - a second containment guard also refuses the mutant, so a mutant assertion would be false evidence.
     The old fabricated checks in `test_packet_a7_reporting.py`, `test_prove4.py`, `test_prove6.py`, `test_prove7.py` are relabelled **"illustration (not a mutation control)"** with pointers to the executed mutants, so no false control claim remains in the packet.

     RETAINED RUNNER includes the new harness: `tests/run.sh` (794 B sha `36e5fd57eab08700d46dbf286f1a595dfcf23a204a81025c54527a65c70d0f90`). Full gate: `./tests/run.sh` rc=0 - 32/32, 22/22, 7/7, 16/16, 25/25, 31/31, 11/11; `./sanity.sh` rc=0.

     PACKET `/tmp/cb-T1-pass10.txt` **85,536 B sha256 `0b597eb446280c43a6132154e3f61463e545d31efd5a52ade3e72b9840328d54`**, `PACKET_BINDS_LIVE_BYTES: True` on 11/11 bindings: `narrator_sfx_batch.py 2c385c5f51ca…`, `sanity.sh 82b388e5e62c…`, `test_packet_a7_reporting.py f9b3f838b7ed…`, `test_prove4.py 6ca85d44e99f…`, `test_prove6.py 0f3eb5185b6b…`, `test_prove7.py 63048abeefe9…`, `test_t1_20_mutation_controls.py 30d252cf50d9…`, `mutant_support.py 2292349f1630…`, `run.sh 36e5fd57eab0…`, `.gitignore cc8d40de55c3…`, `prove_batch.py 9e7682f689dc…`.
     DELEGATED to surf (intercom) with the sha, the attach-as-.md instruction, every bound hash, the per-finding change list, and the request for `VERDICT <file>: PASS|FAIL` per file plus a PACKET VERDICT against those exact bytes. No files were pushed; only working-tree bytes changed.

72. [x] T1 pass-10 verdict APPLIED mechanically — the blocked trigger fired and the whole path ran end to end.
     VERDICT `/tmp/surf-cb-T10/response.md` 15,742 B sha256 `717906735cb4a34e8a4163fcb0716108fa974297a2220495b59adcceb5ae338a`; 12 `VERDICT <file> <sha>:` lines parsed, 11/12 bound to the live file (`prove_batch.py` is the `/tmp/t1fix` proof embedded in the packet, so it has no repo copy); PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py`, all-or-nothing, validated on a copy first:
       - **T1**: `2 PASS` (`tests/test_prove5.py 35cd0d43…`, `tests/test_prove6.py 0f3eb518…`), `4 FAIL` at exactly the reviewed bytes (`narrator_sfx_batch.py 2c385c5f…`, `test_packet_a7_reporting.py f9b3f838…`, `test_prove4.py 6ca85d44…`, `test_prove7.py 63048abe…`).
       - **T1b**: `3 PASS` (`sanity.sh 82b388e5…`, `tests/run.sh 36e5fd57…`, `tests/.gitignore cc8d40de…`).
     Manifest now `5f4eb3105af9b2d000139386bb12f0557489d734572ded04a64f1dfe0f597df7` (27,353 B); FAIL rows carry `review_state=FAILED` and `reviewed_sha256`; PASS rows carry `PASSED` and their reviewed sha.
     INTAKE FIX (real, needed by this packet): one packet spans T1 + T1b + supporting proofs, but the intake refused any verdict naming a file outside the target group. Extras are now REPORTED and not applied, while every row of the target group must still be bound — the all-or-nothing property for the group is unchanged. Intake `87f43b03d697…`.
     REFUSALS-GUARD DEFECT (real, exposed by the applied verdict): `landing-refusals.py` counted `PASS` rows as BLOCKING, so the moment T1b became fully passed the guard cried `SILENTLY LANDABLE — rc=0 with 3 blocking row(s)`. Blocking is now `not startswith(("LANDED", "PASS"))` at both the per-group and manifest level (`3dd46ff4e2d8…`); T1b is correctly non-blocking and landable.
     RECORDS: awaiting cleared for the 9 reviewed rows; the reviewed response registered as an artifact -> coverage `COVERAGE_COMPLETE`; matrix T1 = `PASS` + `FAIL_REPAIR_REQUIRED`, T1b = `PASS` (matrix-check gained a PASS branch that requires a PASS/LANDED row at its current bytes); freeze `ALL_FROZEN`; `landing-gate-doc-check` updated for the applied outcome.
     DOC: the applied PASS/FAIL outcome and the "a PASS row is landable, never blocking" rule recorded and **LANDED `26a99e4affdc…`** (origin blob == local `913eb85e9619…`).
     BOARD: eleven guards **PASS rc=0**, receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e`; parse-check **11/11 MATCH**, receipt `2f3b624c273c5e7a11b3240a161416a02fc9befb553e23e1213c62b802cb16c9`.

73. [x] A7 pass-9 verdict RECEIVED and APPLIED mechanically — first real FAIL intake through the new first-class FAIL path.
     VERDICT `/tmp/surf-cb-A9/response.md` 14,654 B sha256 `02904460e914151a6489e92ad494da884282834d3b8f7daea81b1f660d728275`; every declared hash was verified against the live file before anything was written: `sfx_verify.py 049b11c6e035` MATCH, `spyke_render.py 488a3acb3093` MATCH, `interrupt_sfx.py 8291537eb31a` MATCH, `sfx_policy.py c3c9e92ae5d6` MATCH, `test_prove8.py cc5d77b553d5` MATCH. PACKET VERDICT FAIL.
     APPLIED by `verdict-intake.py --group A7 --report /tmp/surf-cb-A9/response.md --apply` -> **2 PASS, 3 FAIL**, all-or-nothing, validated on a copy first: PASS `sfx_verify.py`, `sfx_policy.py`; FAIL at exactly the reviewed bytes `spyke_render.py`, `interrupt_sfx.py`, `tests/test_prove8.py` (`review_state=FAILED`, `reviewed_sha256` set, `landable_now=false`). Manifest now `f05ec0a4149fa783a12b30f94980193203cb39d969d19b25391202d60ae79bf5`.
     INTAKE/WATCHER FIX (real, found by the first bound-format verdict): the verdict regex could not parse `VERDICT <path> <sha256>: PASS|FAIL` (the \S+? token cannot span the space before the sha), so a genuinely bound verdict would have been refused as having no verdict lines. Regex now allows an optional 64-hex token between the path and the colon; the watcher carries the same pattern. Intake `f55b8b930419…`, watcher `2198e8344150…`.
     RECORDS: A7 removed from `delegations.awaiting` and the reviewed response registered as an artifact -> `packet-group-coverage-v6.py` **COVERAGE_COMPLETE** with `REVIEWED_FAIL=3`, `BOUND_WITH_VERDICT=2`; matrix A7 = `PASS` (2) / `FAIL_REPAIR_REQUIRED` (3), `MATRIX_CONSISTENT`.
     FREEZE FIX (real): `submission-freeze.claimed_sha()` guessed the nearest hash, so it read `sfx_verify`'s sha as `interrupt_sfx`/`test_prove8`'s and reported DRIFT against a correct verdict. It now binds the sha on the file's own `VERDICT` line first (verified: each of the five maps to its own declared hash) -> `ALL_FROZEN`.
     DOC: the applied outcome (pass-9 reviewed, 2 PASS / 3 FAIL, A7 unlandable until repaired) is recorded in `references/verification-evidence.md`, the doc-check expectations updated, **LANDED `cca083c2ff97162d9982ec24a2eccc42cec0bb67`** (origin blob == local `e06508e6d2d6…`).
     BOARD: eleven-guard `board-sweep.sh` **PASS rc=0**, receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e`; `board-sweep-parse-check.py` **11/11 MATCH**, receipt `2f3b624c273c5e7a11b3240a161416a02fc9befb553e23e1213c62b802cb16c9`.

74. [x] A7 pass-9 FAIL findings REPAIRED with executed production mutants; one pass-10 packet delegated.
     SP-20 + SP-18 (`spyke_render.py` 30,428 B sha `6424b2f137e8…`): the rollback candidate name is now UNPREDICTABLE (`secrets.token_hex(6)`), so it cannot replace an existing recovery file, and identity is read from an OPEN descriptor (`os.open` + `fstat`) after the atomic rename instead of a second pathname stat. Executed mutant: reverting to the predictable name DESTROYS a pre-existing recovery file; production preserves it byte-for-byte (`tests/test_a7_pass9_repairs.py` SP-20 pair). SP-15: a forced restoration failure (injected `os.link` error) is reported and the bytes are parked (prove8).
     IS-20 + IS-22 (`interrupt_sfx.py` 35,029 B sha `7baff8b8df4f…`): no `is_file()` substitution — an ABSENT manifest is genuine non-commitment (nothing can reference the clip), while an UNREADABLE/INVALID manifest RAISES into the caller's `unresolved` branch that keeps the clip; the empty-manifest mutant is CAUGHT returning False. Rollback isolates the name with an unpredictable rename and deletes only after `lstat` confirms the moved inode is ours; a replacement inode is left in place. The interrupt-after-clip-link scenario now passes (32/32).
     POL-06 (`sfx_policy.py` 10,925 B sha `a9201737f8e7…`): the Unicode regression case is four DISTINCT non-ASCII tokens (`àéîõü àéîõû àéîöü àéîõô`) — no ASCII at all. Production reports advisory; the ASCII-only-tokenizer mutant accepts it as a cue and is CAUGHT. (The first attempt used an ASCII French sentence, and then a repeated token that is a legitimate non-lexical accept — both recorded as invalid controls, not hidden.)
     A8-PROOF-03 `tests/test_prove8.py` (32,175 B sha `4b65a8a2db8d…`): ownership is OBSERVED (our inode is renamed into the name, then replaced by a foreign inode) instead of an invented `987654321`; the new guard anchor is the real `moved_ino` comparison and the mutant that ignores identity deletes the foreign file. A8-PROOF-06: the FIFO case runs in a BOUNDED child (`subprocess.run(..., timeout=10)`), so a regression is a FAIL rather than a hung harness; timeout=False and the refusal is asserted.
     NEW RETAINED HARNESS `tests/test_a7_pass9_repairs.py` (sha `b0bc4f759096…`) **6/6**; shared `tests/mutant_support.py` (`2292349f1630…`) asserts each mutant anchor occurs exactly once.
     GATES: `./tests/run.sh` rc=0 — 32/32, 22/22, 7/7, 16/16, 25/25, **32/32**, 11/11, **6/6**; `./sanity.sh` rc=0.
     RECORDS: manifest rows for the four changed files re-pointed to `NOT REVIEWED (current artifact)` with `previous_sha256` and `review_packet=/tmp/cb-A7-pass10.txt`; `sfx_verify.py` unchanged keeps its pass-9 PASS; matrix A7 = `PASS` + `cb-A7-pass10`; delegations register the packet and re-point the four rows; harness identity baseline **re-recorded deliberately** (`53e602fd…`) because harness bytes changed.
     DOC: the repair + pass-10 resubmission (sha `57252f7fd1ac…`) is recorded and **LANDED `58f77b4ea9…`** (origin blob == local), after correcting a mistyped 12-hex citation (`57252f7f7d1a` -> `57252f7fd1ac`) that the doc gate caught.
     BOARD: eleven guards **PASS rc=0**, receipt `f50bac12…`; parse-check `SWEEP_REPORT_MATCHES_GUARDS` **11/11**, receipt `2f3b624c…`.
     PACKET `/tmp/cb-A7-pass10.txt` **159,871 B sha256 `57252f7fd1acfb83aa9fcff3281c6cb98769066982ea9975a04fa92f2c39c15e`**, 7 bindings verified (`sfx_verify 049b11c6` unchanged, `spyke_render 6424b2f1`, `interrupt_sfx 7baff8b8`, `sfx_policy a9201737`, `test_prove8 4b65a8a2`, `test_a7_pass9_repairs b0bc4f75`, `mutant_support 2292349f`), DELEGATED to surf as an attached `.md` with the note that `sfx_policy`'s prior PASS no longer applies and `sfx_verify`'s still does.

75. [x] A7 pass-10 verdict APPLIED mechanically — the blocked trigger fired and the path ran end to end.
     VERDICT `/tmp/surf-cb-A10/response.md` sha256 `e48ec5c8ca3307118caf587c25c3ea6508d909776b38ed3b8f118eedec3c55e7`; 7 `VERDICT <file> <sha>:` lines parsed, **7/7 bound to live files** (no unbound). PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py --group A7 --apply`: **PASS** `scripts/sfx_verify.py 049b11c6…`, `scripts/sfx_policy.py a9201737…`; **FAIL at exactly the reviewed bytes** `scripts/spyke_render.py 6424b2f1…`, `scripts/interrupt_sfx.py 7baff8b8…`, `tests/test_prove8.py 4b65a8a2…`. The two supporting verdicts (`mutant_support.py`, `test_a7_pass9_repairs.py`) were reported as out-of-group extras and NOT applied.
     RECORDS: manifest `14191d786ead…` (26,450 B); the five reviewed rows cleared from `awaiting`; the response registered as an artifact; matrix A7 = `PASS`(2) + `FAIL_REPAIR_REQUIRED`(3); FAIL rows carry `review_state=FAILED` and the failed `reviewed_sha256`, so the group stays unlandable.
     DOC: the applied outcome (PASS/FAIL split and the FAIL finding list) recorded in rule 4 and **LANDED `37cd908df180…`**; `landing-gate-doc-check` expectations updated for an APPLIED verdict (matrix set, and PASS/FAIL chosen from each row's own reviewed verdict rather than assuming every non-sfx_verify row failed).
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

76. [x] T1 pass-10 FAIL findings REPAIRED with executed production mutants, and the pass-11 packet is DELEGATED.
     PRODUCTION FIXES (only the four FAIL files plus the two changed PASS files were touched):
       - `scripts/narrator_sfx_batch.py` `680d226ce8d3…`: T1-22 artifact facts (`sha256`, `duration_s`) are carried from the PRIVATE staged artifact / validated sidecar instead of rehashed from the public path; T1-24 metadata identity now includes `id`; T1-28 the credential and request are resolved BEFORE `os.open`, so a missing key no longer leaks the download descriptor.
       - `sanity.sh` `d19f6382a1fb…`: T1-19 now rejects dispatch evidence (`http`, `status`, `400`, `4xx`, `response`) instead of accepting an exit-1 + HTTP 400 as local validation.
       - `tests/test_packet_a7_reporting.py` `bcebb0c335b0…`, `tests/test_prove4.py` `69e48cb7b832…`, `tests/test_prove7.py` `eab919d723a3…`: T1-20's last non-executing "controls" removed rather than left claiming mutation status.
       - `tests/test_t1_20_mutation_controls.py` `5a9d8faa3a76…`: T1-27 `SystemExit(0)/None` is a SUCCESS, not a containment refusal.
       - `tests/test_t1_batch_proof.py` `a6f42943f9c8…` (NEW, in-repo): T1-26 source derived from `__file__`, digest-bound, mutant cut from the same bytes; T1-21 now asserts the INTENDED failure.
     EXECUTED MUTANTS `tests/test_t1_pass10_repairs.py` `8/8`: T1-28 open-before-key mutant leaks fds > 0; T1-24 id-dropped mutant accepts a conflicting sidecar; T1-22 path-rehashing mutant records the mutable digest; T1-21 disabled-generation mutant is caught by a real generation-success control.
     GATES: `./tests/run.sh` **rc=0** (all ten harnesses incl. the new 8/8); `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-T1-pass11.txt` **94,203 B**, sha256 `b8828cc293d137c849e56943b37905997ad23d000206c7d77342e2ae5a644125`, **13/13 bindings verified live** and DELEGATED to surf (six changed rows await it; unchanged PASS rows included for context).
     RECORDS: six changed plan rows re-pointed to the pass-11 packet with `previous_sha256` and `NOT REVIEWED`; matrix T1 = `PASS`(2) + `cb-T1-pass11`(4), T1b = `PASS`(1) + `cb-T1-pass11`(2); plan re-pinned to the same shas; freeze/coverage/board-drift consumers now accept the normalized `{"packet": …}` awaiting shape (three real guard defects exposed by this round).
     DOC: the pass-11 resubmission recorded in rule 4 and LANDED **`80f975a90b43…`** (manifest row re-pinned to the landed blob).
     BOARD: eleven guards **PASS rc=0**, receipt `f50bac124164987b7e61d53ed9ea33e816c003b8b131eeeddd96a2abee94332e`; parse-check **11/11 MATCH** (`2f3b624c273c…`); harness identities deliberately re-recorded (`e2cc06f04c22…`).

77. [x] T1 pass-11 verdict APPLIED mechanically — the blocked trigger fired and the path ran end to end.
     VERDICT `/tmp/surf-cb-T11/response.md` sha256 `53886b5fec151f9c7446d068b4fced57d3d17ce78b0faa64b2f3020440e7a60e`; 13 lines parsed, **13/13 bound to live files**; PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py --apply`: **T1** `2 PASS` (`test_prove5.py 35cd0d43…`, `test_prove6.py 0f3eb518…`) + `4 FAIL` at the reviewed bytes (`narrator_sfx_batch.py 680d226c…`, `test_packet_a7_reporting.py bcebb0c3…`, `test_prove4.py 69e48cb7…`, `test_prove7.py eab919d7…`); **T1b** `3 PASS` (`sanity.sh d19f6382…`, `run.sh 60e4cf47…`, `.gitignore cc8d40de…`).
     RECORDS: manifest `010f7ce1c761…`; nine reviewed rows cleared from `awaiting`; the response registered; matrix T1 = `FAIL_REPAIR_REQUIRED`(4) + `PASS`(2), T1b = `PASS`(3); FAIL rows keep `review_state=FAILED` and the failed `reviewed_sha256`.
     DOC: the applied outcome and the three open findings recorded and **LANDED `cc1b6486f57a…`**; doc-check expectation updated to the applied matrix.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

78. [x] A7 pass-10 FAIL findings REPAIRED with executed mutants, and the pass-11 packet is DELEGATED.
     PRODUCTION (only the three FAIL files changed):
       - `scripts/spyke_render.py` `370e967fcd86…`: SP-18 — after renaming the name to an unpredictable tomb, the rollback opens it with `O_PATH`, verifies inode AND regular-file type, and **never unlinks it**; it restores foreign bytes with a no-clobber link and reports the tomb path ("don't unlink; leave the tomb and report it"). SP-21 — `O_PATH` never reads, so a foreign FIFO cannot block.
       - `scripts/interrupt_sfx.py` `d5e1939738a4…`: IS-22 — the same fix at the generator's tomb (O_PATH + type check, no unlink-by-name; tomb left and named in the outcome).
       - `tests/test_prove8.py` `c587556dfbf7…`: A8-PROOF-03 now observes the "ours" inode from a real file instead of the invented `987654321`; SP-15 observes the parked tomb bytes, not only the internal flag.
     EXECUTED MUTANTS `tests/test_a7_pass10_repairs.py` **7/7**: SP-18 unlink-after-stat mutant is caught (its tomb is gone, baseline's remains); SP-21 `O_RDONLY` mutant blocks on a FIFO and is caught by an 8 s child timeout while the baseline returns; IS-22 static binding verifies neither rollback unlinks a tomb; `test_prove8.py` **32/32**.
     GATES: `./tests/run.sh` **rc=0** (all harnesses incl. 32/32 and the new 7/7); `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-A7-pass11.txt` **164,463 B**, sha256 `4fcb85cff5d1c74eeb9f88d68e57ff0810f216eeca625aacbb59d325c3dc0d87`, **8/8 bindings verified live**, DELEGATED to surf. Changed rows: `spyke_render.py`, `interrupt_sfx.py`, `test_prove8.py`; unchanged PASS rows (`sfx_verify`, `sfx_policy`, `test_a7_pass9_repairs`, `mutant_support`) included for context.
     RECORDS: three rows re-pointed to pass 11 (`previous_sha256`, `NOT REVIEWED`); matrix A7 = `PASS`(2) + `cb-A7-pass11`(3); plan re-pinned; delegations awaiting updated; doc-check now verifies each row against its OWN governing packet (a real gap: it always read the pass-10 packet).
     DOC: the pass-11 resubmission recorded and **LANDED `f95cc292115a…`**.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`); harness identities deliberately re-recorded (`0495f7dd2fd8…`).
     NOTE: `tests/run.sh` was reverted to its T1-pass-11 bytes after I briefly added the A7 harness to it — editing it after delegating T1 would have invalidated that already-submitted packet. The A7 harness is run standalone (7/7) and will join `run.sh` in the next T1 packet round.

79. [x] A7 pass-11 verdict APPLIED mechanically — the blocked trigger fired and the path ran end to end.
     VERDICT `/tmp/surf-cb-A11/response.md` sha256 `beb73715fcc19fa94642d4c7c4a54f11b2e0a06446a096580a2c68669b7d4385`; 8 lines parsed, **8/8 bound to live files**; PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py --group A7 --apply`: **PASS** `scripts/sfx_verify.py 049b11c6…`, `scripts/sfx_policy.py a9201737…`; **FAIL at the reviewed bytes** `scripts/spyke_render.py 370e967f…`, `scripts/interrupt_sfx.py d5e19397…`, `tests/test_prove8.py c587556d…`. The three out-of-group verdicts (`mutant_support.py`, `test_a7_pass9_repairs.py`, `test_a7_pass10_repairs.py`) were reported as extras and NOT applied.
     RECEIVED AS FIXED: **SP-18** (reviewer re-ran the boundary probe; foreign bytes survive) and **SP-21**.
     RECORDS: manifest `70ddce168f0f…`; five reviewed rows cleared from `awaiting`; response registered; matrix A7 = `PASS`(2) + `FAIL_REPAIR_REQUIRED`(3); FAIL rows keep `review_state=FAILED` and the failed `reviewed_sha256`.
     DOC: the applied outcome and the open findings recorded and **LANDED `fb094452c39d…`**; doc-check expectation updated to the applied matrix.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

80. [x] T1 pass-11 FAIL findings REPAIRED with executed mutants, and the pass-12 packet is DELEGATED.
     PRODUCTION: `scripts/narrator_sfx_batch.py` `6a4ed4a5016e…` — T1-29 fixed. `_provenance_record()` reads the sidecar ONCE, validates it against the bytes (`rec["sha256"] == _sha(wav)`), and RETURNS that record; `tts()` uses the returned record and never re-opens the sidecar. The old validate-then-reread path is gone (`_provenance_binds` is now a thin wrapper).
     PROOFS: `tests/test_packet_a7_reporting.py`, `tests/test_prove4.py`, `tests/test_prove7.py` — the remaining comment-only "controls" were deleted (no line claims mutation-control status without executing production code); `tests/test_t1_pass10_repairs.py` — T1-21 now saves and restores the real `tts` in a `finally`, so the generation-success control drives the real generator.
     EXECUTED MUTANT for T1-29: the control swaps the sidecar DURING validation; baseline keeps the validated digest (`existing_verified`, sha = real bytes) while the reread mutant reports the swapped `b`*64 digest and is caught. Harness **10/10** (T1-28 leak, T1-24 id, T1-22 provenance, T1-21 success+disabled, T1-29 single-read+reread).
     GATES: `./tests/run.sh` **rc=0** (`test_packet_a7_reporting 29/29`, `test_prove4 17/17`, `test_prove7 20/20`, `test_prove8 32/32`, `test_t1_20 11/11`, plus all others); `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-T1-pass12.txt` **95,769 B**, sha256 `e42260d6a032b6b794e71f3f122d8cda87eef7f4cb251c3c15300dff3438a0ce`, **13/13 bindings verified live**, DELEGATED to surf. Changed rows: `narrator_sfx_batch.py`, `test_packet_a7_reporting.py`, `test_prove4.py`, `test_prove7.py`; unchanged PASS rows included.
     RECORDS: four rows re-pointed to pass 12 (`previous_sha256`, `NOT REVIEWED`); matrix T1 = `PASS`(2) + `cb-T1-pass12`(4), T1b = `PASS`(3); plan re-pinned; delegations awaiting updated.
     DOC: the pass-12 resubmission and the single-read rule recorded and **LANDED `5dfabb11449d…`**.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`); harness identities deliberately re-recorded (`a56f0dec6cff…`).

81. [x] T1 pass-12b verdict APPLIED mechanically — the blocked trigger fired and the path ran end to end.
     VERDICT `/tmp/surf-cb-T12b/response.md` sha256 `a38bf47b26f5a475cff3c72edd4d336a5498eafb152a32f61a652b907b1bc08e`; 13 lines parsed, **13/13 bound to live files**; PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py --apply`: **T1** `3 PASS` (`test_packet_a7_reporting.py 8af08572…`, `test_prove5.py 35cd0d43…`, `test_prove6.py 0f3eb518…`) + `3 FAIL` at the reviewed bytes (`narrator_sfx_batch.py 0d2fb59b…`, `test_prove4.py 7e64b345…`, `test_prove7.py 76977fdf…`); **T1b** `3 PASS` (`sanity.sh`, `run.sh`, `.gitignore`).
     RECORDS: manifest `eeb8ddc1d77a…`; nine rows cleared from `awaiting`; response registered; matrix T1 = `PASS`(3) + `FAIL_REPAIR_REQUIRED`(3), T1b = `PASS`(3); FAIL rows keep `review_state=FAILED` and the failed `reviewed_sha256`.
     DOC: the applied outcome and the five open findings recorded and **LANDED `c740579f1ede…`**; doc-check updated to the applied matrix.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

82. [x] A7 pass-11 FAIL findings REPAIRED with executed mutants, and the pass-12 packet is DELEGATED.
     PRODUCTION (three FAIL files changed):
       - `scripts/interrupt_sfx.py` `e1869686b174…`: IS-22 — extracted `_rollback_own_clip`; when the rename moves a FOREIGN replacement aside, it is RESTORED at the name no-clobber (duplicate tomb named) instead of leaving the name empty.
       - `scripts/spyke_render.py` `4d69e1613678…`: SP-22 — extracted `_restore_backup`; restoration uses a no-clobber link, so a render completed concurrently after the backup is never erased (backup kept and reported). IS-22's foreign branch restored via the same helper path.
       - `scripts/narrator_sfx_batch.py` `0d2fb59bd53a…`: IS-23 — extracted `_published_digest`; opens `O_NONBLOCK`, requires a regular file and bounds the read to `st_size`, so a FIFO at the published name can no longer block a render.
     PROOFS: `tests/test_a7_pass10_repairs.py` **15/15** (IS-22 restore + no-restore mutant; SP-22 no-clobber + `os.replace` mutant; IS-23 FIFO baseline in a bounded child + blocking-open mutant caught; A8-PROOF-03 OURS branch driven through a real owned file + restoring mutant caught; SP-15 KeyboardInterrupt propagates and bytes survive; SP-21 baselines bounded). `tests/test_prove8.py` **34/34** gained the OURS-branch and KeyboardInterrupt checks. A8-PROOF-08's spelling check was replaced by the executed generator rollback.
     GATES: `./tests/run.sh` **rc=0** (all harnesses); `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-A7-pass12.txt` **171,492 B**, sha256 `d868c4f75a6afad0608877ab38c370e9b83d0483f7208c9f5305036b74105037`, **8/8 bindings verified live**, DELEGATED to surf. Changed rows: `spyke_render.py`, `interrupt_sfx.py`, `test_prove8.py`; unchanged PASS rows included.
     ORDERING VIOLATION FOUND AND CORRECTED: the IS-23 edit changed `narrator_sfx_batch.py` AFTER T1 pass-12 was delegated, so that packet no longer bound the bytes. Rebuilt as `/tmp/cb-T1-pass12b.txt` **96,313 B** sha256 `58c9160f245f…` (**13/13 bindings live**), re-pointed the four governed rows, and sent surf a supersession note; pass-12 (`e42260d6…`) must not be used.
     RECORDS: three A7 rows re-pointed to pass 12; matrix A7 = `PASS`(2) + `cb-A7-pass12`(3); T1 = `PASS`(2) + `cb-T1-pass12b`(4); T1b = `PASS`(3); plan re-pinned; delegations updated.
     DOC: the pass-12 resubmission and the T1 12b supersession recorded and **LANDED `5bfa23733337…`**.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`); identities re-recorded (`a7b282f11c55…`).

83. [x] A7 pass-12 verdict APPLIED mechanically — the blocked trigger fired and the path ran end to end.
     VERDICT `/tmp/surf-cb-A12/response.md` sha256 `670da31cccd1fa22f58ec7f266108b9f39511f8606769fdfd1d7b7e367660679`; 8 lines parsed, **8/8 bound to live files**; PACKET VERDICT FAIL.
     APPLIED with `verdict-intake.py --group A7 --apply`: **PASS** `scripts/sfx_verify.py 049b11c6…`, `scripts/sfx_policy.py a9201737…`; **FAIL at the reviewed bytes** `scripts/spyke_render.py 4d69e161…`, `scripts/interrupt_sfx.py e1869686…`, `tests/test_prove8.py 64172706…`. Three out-of-group verdicts were reported as extras and not applied.
     RECORDS: manifest `a89630e55b97…`; five rows cleared from `awaiting`; response registered; matrix A7 = `PASS`(2) + `FAIL_REPAIR_REQUIRED`(3); FAIL rows keep `review_state=FAILED` and the failed `reviewed_sha256`.
     DOC: the applied outcome and the open findings recorded and **LANDED `f3f1d0f5c03b…`**; doc-check updated to the applied matrix.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).
     REVIEWER OBSERVATION after 12 passes: each repair opens a new race in the same rollback/restore code; replace the rename-dance with ONE primitive (dir_fd + linkat, never unlink what this attempt did not create, leave and report the rest). Recorded in item 84 as the required approach, not an optional cleanup.

84. [x] ONE rollback/restore primitive built, every path rewired onto it, the remaining A7 findings repaired, and A7 pass 13 DELEGATED.
     PRIMITIVE `scripts/fs_ops.py` (NEW, reviewed in the packet): `link_no_clobber` (dir_fd + `os.link(..., dst_dir_fd=..., follow_symlinks=False)`), `park` (unpredictable sibling name; the caller reports it), `read_regular_bounded` (O_NONBLOCK + O_NOFOLLOW + fstat regular + size bound), `unlink_owned` (inode observed through the directory descriptor), `stat_inode`, `digest_regular`. The primitive never unlinks anything.
     REWIRED: `spyke_render` publish / rollback / backup restore / success cleanup; `interrupt_sfx` publish / digest / rollback; `spyke_render.verify_binding` receipt read.
     FINDINGS CLOSED: IS-22 (foreign replacement restored no-clobber, duplicate tomb named); IS-23 (all artifact reads bounded/non-blocking — the reviewer's location was `interrupt_sfx`, and the proof now drives THAT module, A8-PROOF-09); SP-24 (this attempt's names are removed BEFORE backups are restored); SP-25 (`verify_binding` receipt read is bounded/non-blocking, FIFO refused); SP-26 (backup cleanup is ownership-bound); SP-22 retained. Proofs: A8-PROOF-03 drives the OURS branch through a real owned file; A8-PROOF-07 asserts the bounded child's EXIT STATUS, not merely "did not time out"; A8-PROOF-08 executes the generator rollback; SP-15 drives KeyboardInterrupt through the primitive.
     GATES: `./tests/run.sh` **rc=0**; `test_prove8.py` **34/34**; `test_a7_pass10_repairs.py` **19/19**; `test_a7_pass9_repairs.py` **6/6**; `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-A7-pass13.txt` **177,822 B**, sha256 `f475ff3226684d321b8c769cc836ea5e644e4fa0671e6fc9ef7feb5b6fe66226`, **9/9 bindings verified live**, DELEGATED to surf. Changed rows: `spyke_render.py`, `interrupt_sfx.py`, `test_prove8.py`; `fs_ops.py` is the new reviewed module; unchanged PASS rows included.
     RECORDS: three rows re-pointed to pass 13 (`previous_sha256`, `NOT REVIEWED`); matrix A7 = `PASS`(2) + `cb-A7-pass13`(3); plan re-pinned; delegations updated.
     DOC: the primitive and the pass-13 resubmission recorded and **LANDED `8f4ea2f47123…`**.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`); identities deliberately re-recorded (`e7a4aced631e…`).

85. [x] VOID — superseded, not processed. Its packet (`/tmp/cb-A7-pass13.txt`, `f475ff32…`) could no longer bind `spyke_render`/`interrupt_sfx` after `fs_ops.py` gained the T1-33 growth check and the modules gained a self-locating import, so A7 rows were re-pointed to `/tmp/cb-A7-pass13b.txt` (`7a837fc8…`, 9/9 live) and the submission-freeze guard confirmed 13b consistent and 13 not. No verdict on 13 was ever applied, and none will be. Item 87 owns the live packets.

86. [x] T1 pass-12b findings repaired with EXECUTED mutants; T1 pass 13 packet attached and delegated; A7 13b rebuilt for the shared primitive.
     PRODUCTION: `scripts/narrator_sfx_batch.py` `de3741cf…` — T1-32 cache/duration reads go through `fs_ops` (`read_regular_bounded`, `require_regular`, `digest_regular`) so a cached FIFO fails closed BEFORE execute gating; T1-33 growth is refused; T1-30 metadata publication retries a bounded three passes (no recursion) and names the attempt count on failure; T1-24 validation factored into `_validate_meta`/`_META_KEYS` (single anchor, one rule). `scripts/fs_ops.py` `33f8977f…` gained `require_regular` (O_PATH, never blocks) and the post-stat growth read.
     PROOFS: `tests/test_prove4.py` T1-31 requires a NON-ZERO `SystemExit` and keeps the target-unchanged check; the claimed-but-not-run containment/argv/gain comment lines are GONE from `test_prove4.py`/`test_prove7.py` (T1-20). `tests/mutant_support.py` now puts the real source directory on `sys.path` so copied modules import `fs_ops` exactly as production does.
     MUTANTS EXECUTED (`tests/test_t1_pass10_repairs.py` **16/16**): T1-32 cached-FIFO baseline fails closed in ms, blocking-read mutant hangs and is caught by an 8 s child timeout; T1-33 production refuses post-stat growth, no-growth-check mutant accepts the truncated snapshot (caught); T1-30 baseline settles in 3 calls with `ValueError`, recursion mutant dies `RecursionError` at 2,974 calls.
     GATES: `./tests/run.sh` **rc=0** (all nine harnesses PASS incl. prove8 34/34), `./sanity.sh` **rc=0** with a live render.
     PACKETS: `/tmp/cb-T1-pass13.txt` **102,225 B** `1501276439e75ad2a6cd5e59ff3fa6dadb8d99fc12931bbadd2ddd583e734082`, 13/13 bindings live, DELEGATED. `/tmp/cb-A7-pass13b.txt` **179,035 B** `7a837fc8fcc69a834d7f2ddf3443bfec79b38a85f46378971284d009b1aa5e78`, 9/9 bindings live, DELEGATED — 13 could no longer bind `spyke_render`/`interrupt_sfx` after the self-locating import, so A7 rows are re-pointed to 13b and 13 is superseded.
     RECORDS: three T1 rows re-pointed; matrix T1 = `PASS`(3) + `cb-T1-pass13`(3), T1b = `PASS`(3), A7 = `PASS`(2) + `cb-A7-pass13b`(3); plan and matrix re-pinned; delegations registered.
     DOC: pass-13 outcome, the primitive's growth check and the A7 13b supersession recorded and **LANDED `4623887885df…`**; checker updated.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

87. [x] VOID — duplicate of 89, and its A7 packet was superseded. T1 pass 13 (`15012764…`) and A7 13b (`7a837fc8…`) are both covered by item 89, which names the live packets (T1 pass 13 unchanged, A7 **13c** `7b39622f…`). No verdict was applied under this item.

88. [x] A7 pass 13c — surf's 13 findings folded into the shared primitive, gated, packet attached and DELEGATED.
     PRIMITIVE (`scripts/fs_ops.py` `b081ef9b…`): **SP-26** `unlink_owned` PARKS first (unpredictable sibling), verifies the parked inode via `fstat` of an O_PATH fd through the parent `dir_fd`, and unlinks only that verified name — a FOREIGN parked inode is left and reported, never unlinked. **FS-01** `read_regular_bounded` reads to REAL EOF under the cap and requires `total == st_size`; growth and shortfall both refuse (the initial size is never treated as EOF).
     SP-27 (`scripts/spyke_render.py` `75308d97…`): `_restore_backup` stats the backup before linking and verifies `stat_inode(dest) == bak_ino` AFTER; a foreign source returns FAILURE and keeps the backup.
     IS-24 (`scripts/interrupt_sfx.py` `7c1841f1…`): manifest recovery reads through the bounded reader; a non-regular/invalid manifest raises RuntimeError (UNKNOWN state), never an empty manifest. New `_reuse_digest` helper is the one digest path the proof drives.
     PROOFS: A8-PROOF-09 mutates and drives `interrupt_sfx._reuse_digest` (no narrator mutation); A8-PROOF-10 accepts ONLY `TimeoutExpired` as proof of a blocking read; T1-33's mutant follows the EOF-authoritative reader; IS-20's mutant targets the bounded read.
     GATES: `./tests/run.sh` **rc=0** — prove8 **34/34**, A7 repair harness **19/19**, A7 pass-9 harness **6/6**, T1 harness **16/16**, T1 20-controls 11/11, prove4/5/6/7 green; `./sanity.sh` **rc=0** (live render OK).
     PACKET `/tmp/cb-A7-pass13c.txt` **180,715 B** sha256 `7b39622f73755e0420e9813eed51c18824067c69f3cf3bbe7b38d4f2f6504f8b`, **9/9 bindings verified live**, DELEGATED to surf; 13b superseded.
     RECORDS: three A7 rows re-pointed to 13c; matrix A7 = `PASS`(2) + `cb-A7-pass13c`(3); plan and matrix re-pinned; delegations registered.
     DOC: the primitive races and the 13c resubmission recorded and **LANDED `7ac07c5e6830…`**; checker names 13c.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`); identities re-recorded (`63f0a0ad…`).

89. [x] VOID — folded into 91. Its T1 half was APPLIED (pass-13, `eece5bbc…`: 11 PASS / 2 FAIL, recorded in 90 and landed `3a8ea9ea80cb…`), and its A7 half (pass 13c, `7b39622f…`) is now item 91. No verdict was left unprocessed by closing this.

90. [x] T1 pass-13 findings repaired with executed mutants; T1 pass-14 packet attached and DELEGATED.
     PRODUCTION (`scripts/narrator_sfx_batch.py` `38c5739624ba…`):
       - **T1-33** `_published_digest` no longer owns a read loop: it calls `fs_ops.digest_regular`, which reads to real EOF under the cap and requires `total == st_size`, so bytes appended after the fstat are refused. Mutant reverting to `Path.read_bytes()` blocks → caught by an 8 s child timeout.
       - **T1-32** the cache branch calls `fs_ops.require_regular` before trusting or hashing the artifact (and `_duration` does too). Mutant removing the guard AND using a blocking read → caught by timeout; the BASELINE finishes within the deadline.
       - **T1-34** all existing-metadata reads funnel through one `_read_meta` helper using `read_regular_bounded`; a FIFO at the metadata name is UNKNOWN state (ValueError), never a blocking read. Mutant (`exists()` guard + `read_text()`) → caught by timeout.
       - **T1-35** the baseline cached-FIFO probe now runs in a bounded child with an 8 s deadline; not finishing fails the check.
     PROOFS: `tests/test_t1_pass10_repairs.py` **21/21** (T1-32/T1-33/T1-34/T1-35 each with a caught production mutant); T1-33's `fs_ops` size-check mutant and T1-30's recursion mutant still caught.
     GATES: `./tests/run.sh` **rc=0** (prove8 34/34, A7 harness 19/19, pass-9 6/6, prove4 17/17, prove7 20/20); `./sanity.sh` **rc=0** with a live render.
     PACKET `/tmp/cb-T1-pass14.txt` **107,046 B** sha256 `fee9288cfe0024ffc4475d24b678583a6a89808ed8b3a82d2fcd5c17a11020ab`, **13/13 bindings verified live**, DELEGATED to surf. Row re-pointed: `narrator_sfx_batch.py`; the failing support harness `test_t1_pass10_repairs.py` is in the packet at its current bytes but is not a plan row.
     RECORDS: narrator re-pointed (`previous_sha256`, `NOT REVIEWED`); matrix T1 = `PASS`(5) + `cb-T1-pass14`(1), T1b = `PASS`(3); plan and matrix re-pinned; delegations updated.
     DOC: pass-14 resubmission recorded and **LANDED `ed0c63e26f5d…`**; checker names pass 14.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse-check **11/11 MATCH** (`2f3b624c…`).

91. [x] A7 pass-13c verdict APPLIED mechanically (T1 pass-14 still awaiting its verdict and is now item 92's concern).
     VERDICT `/tmp/surf-cb-A13c/response.md` sha256 `6dc040f25255833b06e47c554664f274cda84df509ec6d71d006d70bb68162f9`; 9 lines parsed, **9/9 bound**; PACKET VERDICT FAIL.
     APPLIED (`verdict-intake.py --group A7 --apply`): **PASS** `sfx_policy.py a9201737…`, `test_prove8.py 3d690df7…`; **FAIL** at the reviewed bytes `interrupt_sfx.py 7c1841f1…`, `sfx_verify.py 049b11c6…`, `spyke_render.py 75308d97…`. Four out-of-group verdicts reported and NOT applied: `fs_ops.py` FAIL (SP-26 partial), `test_a7_pass10_repairs.py` FAIL (A8-PROOF-09 partial), `test_a7_pass9_repairs.py` PASS, `mutant_support.py` PASS.
     NOTE: `sfx_verify.py` was PASS while byte-unchanged and this review found SV-26/SV-27 in it; its earlier PASS no longer holds.
     RECORDS: manifest `80aedd23…`; all A7 rows cleared from `awaiting`; matrix A7 = `PASS`(2) + `FAIL_REPAIR_REQUIRED`(3); FAIL rows keep `review_state=FAILED` and the failed `reviewed_sha256`.
     DOC: applied outcome and open findings recorded and **LANDED `137619b61f8f…`**; checker updated.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse **11/11 MATCH** (`2f3b624c…`).

92. [x] A7 pass-13d findings repaired with executed mutants; A7 pass-14 packet DELEGATED; T1 packet rebuilt as pass 15 (pass 14 superseded).
     PRODUCTION:
       - **SP-26** `scripts/fs_ops.py` `a073542a…`: production STOPS DELETING. `retire_owned` parks the name, verifies the parked inode via O_PATH fstat, and returns `("retired"|"foreign", tomb)`; there is NO unlink anywhere, so the parked-name window is gone. A foreign occupant is left parked and reported by name.
       - **SP-27** `scripts/spyke_render.py` `ec294a2b…`: backup inode verified when moved aside (mismatch raises + rollback), re-verified before every restore (mismatch = NOT restored + failure), and destination inode verified after install (mismatch = FAILURE).
       - **SV-26/SV-27** `scripts/sfx_verify.py` `5eb35a96…`: after publish the report is re-read through the bounded reader and its digest compared to the staged body (mismatch or failed re-read = write FAILED); payload serialisation and per-entry validation are guarded so hostile/rejected manifest data produces a failure row instead of aborting before the report.
       - **IS-25** `scripts/interrupt_sfx.py` `584723f1…`: commit re-reads the manifest through `fs_ops.read_regular_bounded`; absent = empty library, anything unknown (FIFO/dir/unreadable/invalid) raises and refuses the commit.
       - **IS-26**: reuse read catches `(OSError, ValueError)` so one clip cannot abort the batch.
       - **A8-PROOF-09**: baseline AND mutant drive `interrupt_sfx._reuse_digest`, with module identity asserted.
     PROOFS: `tests/test_a7_pass10_repairs.py` **33/33** (one caught production mutant per finding: SP-26 unlink-after-park, SP-27 no-inode-check, SV-26 no-published-compare, SV-27 unguarded serialisation, IS-25 unknown-read-as-empty, IS-26 ValueError-only); `tests/test_packet_a7_reporting.py` **30/30** — its old "no backups left behind" assertion encoded the deleted-backup contract, so it now asserts the parked tomb and that it still holds the original bytes.
     GATES: `./tests/run.sh` all retained harnesses PASS; `./sanity.sh` **rc=0** — live render `NOT_ESTABLISHED (service down)` because `:8018` was stopped for the researcher's GPU probe.
     PACKETS: `/tmp/cb-A7-pass14.txt` **191,343 B** `77aab3cebf11e369a7a2ea14b491085c88e86a7c251ebcf7bd11470bfd4e6583`, 9/9 bindings live, DELEGATED. T1 rebuilt as `/tmp/cb-T1-pass15.txt` **106,853 B** `8d139f51a08af406404dea889d9a7cca415c2e59b7057911348cdc094a5b9222`, 13/13 live, because the SP-26 repair changed `test_packet_a7_reporting.py`; every T1 row moved to it. T1 pass-14's verdict then correctly REFUSED intake (its PASS row no longer matches the current sha), so it is superseded, not applied; its findings are item 93.
     DOC: A7 pass-14 + T1 pass-15 supersession recorded and **LANDED `468cc29e7bf4…`**.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse **11/11** (`2f3b624c…`); identities re-recorded deliberately (`440cafa4…`).

93. [x] T1 pass-14 findings repaired with executed mutants; `scripts/fs_ops.py` bound in the packet; proofs drive the NARRATOR call sites; T1 pass-16 packet DELEGATED.
     PRODUCTION: `scripts/narrator_sfx_batch.py` `1d3bbdcd9e20…` — **T1-36** `_manifest_update` reads the manifest through `fs_ops.read_regular_bounded` INSIDE the exclusive lock; absent = empty library, anything unknown raises, so a FIFO cannot park the lock holder.
     PROOFS (`tests/test_t1_pass10_repairs.py` `24/24`, one caught production mutant each):
       - **T1-32/33/34** now drive the NARRATOR call sites: `tts(...)` in a timed child for cached-FIFO baseline AND mutant; `_published_digest(...)` with an fstat stub for the EOF case; `_ensure_meta(...)` for the metadata FIFO.
       - **T1-35** the direct `fifo_cache_probe(base)` call is REMOVED; the baseline runs only inside the 8 s timed child.
       - **T1-36** FIFO manifest refused inside the lock; mutant `MANIFEST.read_text()` times out.
       - **T1-37** the control DISCRIMINATES the EOF defect: fstat stub reports 5 bytes for a 10-byte file, production returns None while the size-check-removed mutant returns a digest, so the control fails if the rule is removed.
       - **T1-38** the metadata fixture pins `Path.is_file` open for that one path so the read reaches `_read_meta` through `_ensure_meta`'s real guard.
     EVIDENCE LIMIT CLOSED: `/tmp/cb-T1-pass16.txt` binds `scripts/fs_ops.py` at `a073542a…`, the same bytes A7 pass 14 binds.
     GATES: all retained harnesses PASS; `./sanity.sh` rc=0 with the live render `NOT_ESTABLISHED (service down)` because `:8018` was stopped for the researcher's GPU probe.
     PACKET `/tmp/cb-T1-pass16.txt` **116,492 B** sha256 `dc42a39c00b75f7ab1a7bb825e9629747c8ec91ce84cf0af192cd52bbe74245e`, **14/14 bindings verified live**, DELEGATED to surf; pass 15 superseded.
     RECORDS: narrator + `test_packet_a7_reporting.py` re-pointed; matrix T1 = `PASS`(4) + `cb-T1-pass16`(2); plan and matrix re-pinned.
     DOC: T1 pass-16 recorded and **LANDED `ae2cfd9d3cee…`**; checker names pass 16.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse **11/11** (`2f3b624c…`).

94. [x] T1 pass-16 verdict PROCESSED (item narrowed to T1 after A7 was applied).
     `/tmp/surf-cb-T16/response.md` `a22e4c257762…`: **13 PASS, 1 FAIL**; every production file PASS, only `tests/test_t1_pass10_repairs.py` FAILED on T1-39 (baselines called inline could hang the gate).
     Applied via `verdict-intake.py --group T1 --apply` (13 PASS bound to reviewed bytes); the FAIL exposed a missing manifest row and was recorded first-class at `000f4e47…`, then repaired and re-submitted as T1 pass 17 (`2b81ad98…`, item 97).
     OWNER: closed by application + repair, no residual work here.

95. [x] Codec round-trip probe RETURNED (researcher, isolated container). Result SUPPORTS the "tokens alone do not carry the SFX" hypothesis, with a stated confound.
     RECEIPT `/tmp/codec-probe-77/receipt.json` 5,624 B, **12 rows** (6 clips x 2 conditions); disposable container exited rc0 and was removed; `:8018` RESTARTED and `GET /health` returned **200** (8 checks). Prior failure was CUDA OOM at `ve.to(device)` with the service resident.
     MEASURED (log-mel Pearson, fixed 10 ms alignment, no DTW):
       clip            self   neutral
       cough-clear     .939   .767
       laugh-full      .920   .747
       sigh-shaky      .896   .655
       sigh-weary      .907   .746
       speech-seed0    .950   .927
       speech-seed1    .963   .941
     READING: **speech controls stay high under a NEUTRAL reference (.927/.941); every SFX collapses (.655-.767).** Self-reference reaches 5/6 at >=.90 (median .930) but self-reference also supplies continuous acoustic conditioning, so that column does NOT isolate discrete vocabulary capacity. The discriminating column is neutral, and it says the discrete token stream does not carry the non-lexical character on its own.
     DECISION BOUNDARY: this is evidence that the current speech-token vocabulary is not sufficient for model-native SFX, not proof of impossibility; the self-reference confound and the fact that the controls are same-text/different-seed Embry renders (not verified same-speaker controls for the SFX) are recorded limitations, and there is NO listening verdict. Production mechanism remains verified WAV clips spliced at sentence boundaries; model-native SFX would require a tokenizer/codec change, which is a new campaign, not a T3 prompt fix.
     CORRECTION RECORDED: the EL-sigh LoRA bar result is **2/8 seeds**, not 2/6.

96. [x] A7 pass-14 findings repaired with executed mutants; A7 pass-15 packet DELEGATED.
     PRODUCTION (current bytes): `fs_ops.py` `a073542a…` (SP-26 stays closed; SP-27 now uses one recorded observation), `spyke_render.py` `65e96e9e…` (SP-27 single-observation restore, SP-28 park-on-cleanup, SP-29 published-digest proof), `interrupt_sfx.py` `1e51f577…` (IS-25 `_load_manifest` for startup/footer, IS-27 restored-inode verification), `sfx_verify.py` `05e0eab4…` (SV-26 staged-inode check + parked leftovers, SV-27 surrogate-safe reservation/serialisation).
     PROOFS `tests/test_a7_pass10_repairs.py` **42/42**, caught mutants each: SP-27 post-link check removed (reports success) vs production refuses; SP-28 park vs unlink (nothing parked); SV-26 staging identity ignored (publishes) vs production refuses; IS-27 restored-inode check removed (claims restore) vs production says UNVERIFIED; SV-27's exact input `{"entries":[{"id":"x","category":7,"file":"/\ud800"}]}` gives **rc=2 AND a FAIL report**.
     GATES: all retained harnesses PASS (packet 30/30, prove8 34/34, pass-9 6/6); `./sanity.sh` **rc=0** with a live render.
     PACKET `/tmp/cb-A7-pass15.txt` **199,374 B** sha256 `4d4b7b88111de7fd1e350ff34a58a2c2b8be2071299a3595f960bea253da9835`, **9/9 bindings live**, DELEGATED to surf.
     RECORDS: three A7 rows re-pointed; matrix A7 = `PASS`(2) + `cb-A7-pass15`(3); plan and matrix re-pinned; delegations updated.
     DOC: pass-15 recorded and **LANDED `7528d7c51146…`**; checker names pass 15.
     BOARD: eleven guards **PASS rc=0** (`f50bac12…`), parse **11/11**; identities re-recorded deliberately (`1df0a36d…`).

97. [x] T1 pass-17 verdict PROCESSED and LANDED (after correcting my own false claim in this item).
     VERDICT: PACKET **PASS**, 14/14 files PASS, no findings. `/tmp/surf-cb-T17/response.md` `dc0356cb4c8a…`, binds packet `/tmp/cb-T1-pass17.txt` `2b81ad98…` (response newer than packet; every file hash re-verified against disk, drifted none).
     APPLIED: `verdict-intake.py --group T1 --apply` bound 13 rows; `tests/test_t1_pass10_repairs.py` was skipped by intake, so its PASS was bound mechanically from its own verdict line at `7ed5445d…` (not hand-written).
     LANDING — CORRECTION: my first record said "files identical to origin/main, no push required". That was FALSE: `git ls-tree origin/main` returned nothing for both paths (the empty-blob hash `e3b0c442…` is not the file). Both files were NEW on origin/main.
     ACTUAL LANDING: `gh-land` with a JSON reviewer receipt (`/tmp/reviewer-receipt-t1-pass17.json`, `5ef9cf3ba228…`, `greenfield=true` + requirement restatement, because these are new source paths). Receipt validation: `{"valid": true, "reviewer_provider": "openai"}`; secret scan "no leaks found"; **commit `7d290c89aafaf00eaddae3fafb5c2161b75eb125`** on origin/main.
     ORIGIN VERIFICATION (re-read after push): `test_t1_pass10_repairs.py` origin `7ed5445d15df` == local; `tests/run.sh` origin `11fc4e3faf99` == local. Both MATCH.
     BOARD: eleven guards **PASS rc=0**, parse **11/11** (`2f3b624c…`). Delegation records restored for 11 PASS rows so coverage sees a governing packet.
     OWNER: closed with commit + blob verification.

98. [x] Codec DISCOVERY/FEASIBILITY MVP COMPLETE (owner-approved zero-shot variant) — **PASS**, and it settles the "can tokens carry SFX" question.
     RECEIPT `/tmp/codec2/receipt.json` **73183 B** sha256 `259e8bb199622b301c1df57ad0516b349408dbb63f50922857156e9b34ae33d6`; verdict `/tmp/codec2/verdict.md` sha256 `33d05a21652513d52e24b9d0cc647ff088b8b56c322ed86a90a280739d731fb0`.
     CODEC: `descript-audio-codec 1.0.0` DAC 44 kHz 8 kbps (9 codebooks x 1024, ~**774 codes/s**), CPU; no service or GPU touched.
     TRAINING: **NOT RUN — BLOCKED_DATA_RIGHTS** (no rights-clean train split; the manifest carries no license/source field). Correctly reported as a blocker, not a failure.
     EVAL: frozen `eval-freeze-v1.json` (**74 clips**, sha `876542cfc437…`), immutable, all digest-verified against the 83-entry manifest.
     MEDIANS (token-only, no clip acoustics as reference): pretrained DAC log-mel **.985**, envelope .998, centroid .974, RMS .987; random-init -.035/.178/3.864/.525 (representation floor); shuffled-token .504/-.054/.828/.495 (token identity matters). **12/12 SFX categories >= .85**; speech controls .988.
     DECISION RULE (pre-declared): median >= .90 AND >= 2/3 categories >= .85 -> **PASS**.
     THE CAPACITY CAVEAT THAT MATTERS: DAC emits ~774 discrete codes/s vs S3's **25 codes/s at 16 kHz**. So this shows the CURRENT S3 speech codec is the binding constraint, not that non-speech cannot be represented in discrete tokens. It also means a model-native-SFX campaign would need a high-rate codec (and then T3 retraining + adapter invalidation), not a vocabulary tweak.
     SCOPE (verbatim from the receipt): pre-trained open codecs represent non-speech SFX near-losslessly from tokens alone; says nothing about fine-tuning on a rights-clean corpus, no deployment or engine change implied; speech controls are Embry same-text/different-seed renders, not matched-speaker controls for SFX.
     CONSEQUENCE FOR PRODUCTION: unchanged — verified WAV clips spliced at sentence boundaries remain the live mechanism (3/3 effective). This result is capacity evidence, not an engine decision.
     CORRECTION CARRIED: the EL-sigh LoRA bar is **2/8 seeds**, not 2/6.

99. [x] A7 pass 16: all six pass-15 findings closed with controls that FAIL when the guard is removed; packet DELEGATED.
     PRODUCTION (current bytes): `spyke_render.py` `82ce3d3b…` (SP-30 staged inode threaded from the written descriptor through `_publish`, no second stat of the name; SP-28 success path PARKS staging), `interrupt_sfx.py` `311be625…` (IS-28 manifest staging verified before `os.replace`, leftovers parked; A8-PROOF-09 `_reuse_outcome` is the production reuse decision the loop calls), `sfx_verify.py` `94cc0598…` (SV-26 explicit staging outcome + published inode must equal staged inode).
     PROOFS `tests/test_a7_pass10_repairs.py` **48/48** with caught mutants for SP-30 (staged inode changed → production refuses, mutant publishes), SP-28 (success parks vs unlinks), SV-26 (both guards removed → mutant publishes), IS-28 (staging identity ignored → mutant commits), A8-PROOF-09 (blocking reuse decision times out), IS-26; A14-PROOF-01 now injects the mismatch for the mutant destination too.
     GATES: `test_prove8.py` **34/34** after its ownership-recording anchor was re-pointed at the SP-30 line; `tests/run.sh` **rc=0**, all retained harnesses PASS; `./sanity.sh` **rc=0** with a live render.
     PACKET `/tmp/cb-A7-pass16.txt` **205,430 B** sha256 `d78b86c195e2cf1a56ac0b9277ca3f1211ad2475200f65b8f3ae6c904fd5595a`, **9/9 bindings live**, DELEGATED to surf. It SUPERSEDES the `f4e13396…` build (assembled before the `test_prove8.py` anchor fix; never submitted); that reason is recorded in the doc.
     RECORDS: A7 rows re-pointed (5 need pass 16: spyke_render, interrupt_sfx, sfx_verify, test_prove8, test_a7_pass10_repairs; 1 PASS remains); matrix A7 = `PASS`(1) + `cb-A7-pass16`(5); plan pinned; delegations updated; pass-15 FAIL state cleared before delegation so no verdict sits on moved bytes.
     MISSING-ROW DEFECT REPEATED AND FIXED: `tests/test_a7_pass10_repairs.py` had NO manifest row either (same as the T1 harness), so its pass-15 FAIL was not first-class. A row was added before re-pointing.
     DOC **LANDED `fd26310fec2c…`** (records the rebuild reason and the cleared FAIL state); checker expectation updated to the derived needs set.
     BOARD: eleven guards **PASS rc=0**, parse **11/11**; identities deliberately re-recorded `70b468523ba4…`.
     Verification commands: `python3 tests/test_a7_pass10_repairs.py` → 48/48; `bash tests/run.sh` → rc=0; `./sanity.sh` → rc=0; packet binding re-hash → 9/9, drifted none.

100. [x] A7 pass-16 verdict PROCESSED: PACKET VERDICT **FAIL**, 7 PASS, 2 FAIL, one finding class.
     `/tmp/surf-cb-A16/response.md` `a37cc3280a7a03fe…` (sentinel `WEBGPT_DONE:20261113T010903Z:4d9df6e0`), binds packet `/tmp/cb-A7-pass16.txt` `d78b86c1…`; 9/9 verdict hashes re-verified against live bytes, drifted none.
     PASS at reviewed bytes: `fs_ops.py`, `sfx_verify.py` `94cc0598…` (SV-26/SV-27 confirmed closed), `sfx_policy.py`, `test_prove8.py` `d2314b9e…`, `test_a7_pass9_repairs.py`, `mutant_support.py`, `test_a7_pass10_repairs.py` `be201f7a…` (that row intake skipped; its PASS was bound mechanically from its own verdict line at live bytes).
     FAIL at reviewed bytes: `spyke_render.py` `82ce3d3b…` (SP-30 PARTIAL, :487-496, 630-639) and `interrupt_sfx.py` `311be625…` (IS-28 PARTIAL, :465-475) — the SAME name-based check-then-act race.
     APPLIED via `verdict-intake.py --group A7 --apply`; matrix A7 now `PASS`(4) + `FAIL_REPAIR_REQUIRED`(2); doc **LANDED `21aa294e850c…`**; board eleven guards **PASS rc=0**.
     OWNER: closed by application; the repair is item 107.

101. [x] `wav_guard.py` packet REBUILT at current bytes and DELEGATED.
     PACKET `/tmp/cb-wg-pass2.txt` **14,009 B** sha256 `08c9be03403bf6c3d97a468d86800a2dde8e5e120188560c60300e72fe43b364`; binding **verified live**: `scripts/wav_guard.py` = `998b2cdfc9f7…`.
     WHY: the old packet (`/tmp/cb-wg-review.txt`, `181d05b5…`) bound older bytes and its only response is `STALE_RESPONSE_SUPERSEDED` (`surf-cb-A6`); nothing had been landed on its PASS.
     CONTENTS: the full current file, the four landing invariants (container-not-200, AC-component health with a floor, deterministic reporting, fail-closed `WavError`), the accepted contract (acoustic profiles are plausibility filters, NOT event recognisers; ASR advisory only), and the landed thresholds `ACTIVE_WINDOW_S=0.02`, `ACTIVE_AC_RMS=0.005`, `MIN_AC_RMS=0.0025`, `MIN_ACTIVE_FRAC=0.15`.
     DELEGATED to surf with the exact hash and reply format; records updated (manifest row `NOT REVIEWED (current artifact)`, delegations awaiting, matrix `GUARDS-WAVGUARD` = `cb-wg-pass2`, plan pinned).
     DOC **LANDED `ba453d260176…`**; board **eleven guards PASS rc=0**, parse **11/11** (`2f3b624c…`).
     Next legal move: `verdict-watch.py --require-ready` → `verdict-intake.py --group GUARDS-WAVGUARD --apply` → `landing-check.sh GUARDS-WAVGUARD` → land only PASS rows with the receipt → sweep + parse (item 102).

102. [x] Surf transport outage RESOLVED and its consequence already handled — this item is closed, not waiting.
     OUTAGE AS RECORDED: stale CDP on tab 837460216 (`status=prepared_prompt`, `submitted_to_chatgpt=False`, verbatim
     "no prompt submitted and no fallback tab created") and submit_failed/delivery_not_proven on tab 837460209.
     RESOLUTION (surf's repair, verified here): the failed attempt is preserved at /tmp/surf-cb-WG2.failed1;
     /tmp/surf-cb-WG2/response.md.receipt.json now reads status=submitted_to_chatgpt, submitted=True; the delivered
     response is /tmp/surf-cb-WG2/response.md sha256 c0bf6b9a9186428d03c524541f36d8c50df2c3e6f8f7a752168252840cb42df7
     (surf's own report: closed the stale tab, fresh tab bound at /tmp/cb-tab).
     CONSEQUENCE DISCHARGED: that submission was the wav_guard review, and it came back FAIL. The verdict was applied
     first-class (item 127: 0 PASS, 1 FAIL, manifest 34,662 B sha256 24aaed8f), all three findings (WG-06/07/08) were
     reproduced with the reviewer's exact inputs and repaired, and the replacement packet is /tmp/cb-wg-pass3.txt
     (12332dc9, 4/4 bindings) awaiting verdict under item 132. Nothing from this outage is left unhandled.
     ALSO SETTLED BY THE OUTAGE PERIOD: B4a/B4b are reviews of older packets (09b0e220, 18dcd308) whose
     delivery_not_proven meta is a known false negative in surf's user-turn check; their text binds nothing and was
     not applied. B4 pass 2 (0a4b338d) and pass 4 (e7e9c1e0) are superseded by pass 5 (53186cca).
     Verification: receipt submitted=True; response sha c0bf6b9a; failed1 dir present; verdict applied at 127.
117. [x] A7 pass-16 PASS rows LANDED (unblocked work done while surf's transport outage holds the FAIL rows).
     WHAT LANDED: `skills/chatterbox-speak/scripts/sfx_verify.py` (`94cc059802b3…`, was ABSENT from origin) and
     `skills/chatterbox-speak/scripts/sfx_policy.py` (`a9201737f8e7…`, origin held an older blob) — commit
     **`f7bf7159596a3937c7aa885c0dc8a1c7c1d8da05`**, landed with the JSON reviewer receipt
     `/tmp/reviewer-receipt-a7-pass16-passrows.json` (`07577f8acea8…`, reviewer `openai` / author `zai`,
     `greenfield=true`).
     AUTHORITY: both files were PASSed by the A7 pass-16 review at exactly these bytes —
     `VERDICT scripts/sfx_verify.py 94cc0598…: PASS` and `VERDICT scripts/sfx_policy.py a9201737…: PASS`
     (`/tmp/surf-cb-A16/response.md` against packet `d78b86c1…`). Nothing from the two FAIL rows
     (`spyke_render.py` SP-30, `interrupt_sfx.py` IS-28) was carried in; those stay unlandable until pass 17.
     READ-BACK: `git show origin/main:<path> | sha256sum` matched the live bytes for both files (MATCH/MATCH),
     not the empty-blob hash.
     BOOKKEEPING AFTER THE LANDING (each drift caused and then cleared): record commit **`4761d99ad008…`**
     (doc), plan rows removed for landed paths + Markdown twin aligned, matrix provenance re-pinned to the
     current plan/manifest, doc-checker `A7_PATHS` reduced to the three rows still under review.
     BOARD: eleven guards **PASS rc=0** after the repair.
     Verification: live/origin hash compare -> MATCH, MATCH; `git log -2 origin/main` -> `4761d99ad0`, `f7bf715959`; board sweep -> PASS (11 guards).

118. [x] Ear-review verdict path PROVEN END-TO-END on an isolated manifest (the owner's listening session cannot silently lose verdicts).
     METHOD: `/tmp/rv-test/serve.py` imports `listen_review` with `MANIFEST` overridden to a COPY of the library manifest and serves on an unused port **:8851**; production was never in the write path.
     EVIDENCE: `GET /api/clips` -> 200, **74 pending**; `POST /api/verdict {"id":"alex-chuckle","verdict":"human_confirmed"}` -> **200 `{"ok": true, "id": "alex-chuckle", "status": "human_confirmed"}`**; the copy's entry then read `status=human_confirmed` with `reviewed_at_utc` set, and `GET /api/clips` returned **73** — so the write persists and the pending list shrinks.
     PRODUCTION UNTOUCHED (verified): the library manifest is still 70,752 B sha `2b0897083f26…`, mtime `2026-11-12 11:55`, statuses unchanged at `awaiting_owner_verdict` 74 / `excluded_nonconforming` 6 / `culled_content_failed` 3.
     CLEANUP: isolated server stopped; `:8851` has no listener and no `rv-test/serve.py` process remains.
     Verdict schema for the record: `Verdict(id: str, verdict: Literal["human_confirmed","rejected","skipped"])`; the handler sets `status` + `reviewed_at_utc` and rewrites via tmp+replace.
     WHY THIS MATTERS: item 11 is blocked purely on the owner's ear; this proves the tooling records what he does.

119. [x] Frozen eval RE-VERIFIED against the library after today's surface/landing work — no drift, no need for a v2.
     EVIDENCE: `sfx-library/eval-freeze-v1.json` is **26,373 B** sha256
     `876542cfc4377f554d836bc49413f37e4d29489b1911cb461ffaa5b0bb9fe3b9` — **identical to the recorded freeze hash**, so the artifact is the one that was frozen.
     CONTENT: **74 entries** (keys `category, file, id, seconds, sha256, status, voice`); cross-checked entry-by-entry against `manifest.json` on `sha256`, `category`, `file` and status -> **0 mismatches**; every frozen entry is still `awaiting_owner_verdict`, and the library still holds exactly **74 awaiting** with 6 `excluded_nonconforming` and 3 `culled_content_failed` excluded from the freeze.
     MEANING: the 74-clip eval the researcher's codec result was measured on is the same set the owner's `:8797` surface now serves; no clip moved, no hash moved, so `eval-freeze-v1` stays immutable and no supersession is needed.
     Verification: `sha256sum eval-freeze-v1.json` -> `876542cf…`; entry-wise comparison script -> 0 mismatches, 74 awaiting.

120. [x] A7 pass 17 was INCOMPLETE — two name-based publish sites remained; both now publish from the descriptor, and pass 18 is delegated.
     FOUND BY: auditing every `fs_ops` call site after the refactor (not by a reviewer).
     - `scripts/sfx_verify.py` `5fa6cf721a6a…`: had `mkstemp` + `stat_inode(tmp_name)` + `os.link(tmp_name, out)`. Now `fs_ops.stage_bytes` (O_TMPFILE — no name exists), `link_fd_no_clobber`, a refusal when the published inode is not the staged descriptor's, returned diagnostics (never raises), and any fallback staging name parked.
     - `scripts/interrupt_sfx.py` `142c00d14638…`: `_publish_no_replace` used `link_no_clobber(staged_path, dest)`. Now opens the staged clip read-only, captures the descriptor inode, publishes from the descriptor, verifies the destination inode.
     HARNESS ENFORCEMENT MOVED WITH THE CODE (each control fails when its guard is dropped): `tests/test_a7_pass10_repairs.py` `dc5a66d11c49…` **49/49** — SV-26 refuses a foreign published inode and a foreign staging claim, each with a mutant that publishes when the comparison is dropped; `test_prove8.py` `2c39639f54d9…` 34/34 (its staging fault now targets `stage_bytes`); `test_packet_a7_reporting.py` `206051d6…` 30/30 (its race now fires at `link_fd_no_clobber`); `test_t1_20_mutation_controls.py` `80f6e8f2…` rc=0.
     GATES: `tests/run.sh` **rc=0** (all retained harnesses PASS), `./sanity.sh` **rc=0** with a live render.
     PACKET `/tmp/cb-A7-pass18.txt` **220,032 B** sha256 `6076a8f2c19e7a892aecc313d828eba578e95e11f3998924d19d708c4a028f96`, **10/10 bindings re-hashed, drifted none** — SUPERSEDES the unsubmitted pass 17 (`0c265759…`), which must NOT be submitted.
     RECORDS: 10 rows re-pointed to pass 18; matrix A7 = `cb-A7-pass18`(10); `sfx_policy.py` restored to its LANDED verdict (my first rewrite clobbered it); plan pinned; delegation recorded; doc **LANDED `d12e3ffa8b13…`**; identities re-recorded `0e044330…`.
     BOARD: eleven guards **PASS rc=0** (after clearing four drifts this rewrite caused), parse-check matches guards.
     DELEGATED to surf with the packet hash and the explicit instruction not to submit pass 17.
     Verification: binding re-hash -> 10/10 none drifted; `bash tests/run.sh` -> rc=0; `./sanity.sh` -> rc=0; board sweep -> PASS (11 guards).

121. [x] WITHDRAWN — A7 pass 18 is dead, not awaiting: 7 of its 10 bindings drifted after pass 22 changed fs_ops, spyke_render, interrupt_sfx and the harnesses. Earlier drift checks: pass 18 rebuilt/hash 2579bbe6, pass 20 hash b3757e9b. Both are superseded by pass 22 (519eab28) and were never submitted.
122. [x] Name-based publishes outside the A7 scope: three modules rewired to descriptor publication, `arc_chart.py` triaged with a stated reason, packet pass 19 delegated.
     FINDING (from auditing every `fs_ops` call site, not from a reviewer): the fixed pattern existed in three modules and the unfixed one in four.
     FIXED — `scripts/narrator_sfx_batch.py` `87af44926aff…`: `_publish_no_replace` opened the clip read-only and installs from the DESCRIPTOR via `_publish_fd_no_replace` -> `fs_ops.link_fd_no_clobber`, verifying the destination inode; the MANIFEST commit moved from `mkstemp` + `os.replace(tmp, MANIFEST)` to `stage_bytes` + `replace_from_fd`; the meta sidecar stages and publishes through one descriptor and PARKS a fallback name instead of unlinking it. `scripts/speak.py` `376982581e14…`: `mkstemp` + `os.replace(tmp, p)` -> `stage_bytes` + `replace_from_fd`. `scripts/review_store.py` `abd4837a4dbb…`: `open('x')` + `os.link(temporary, path)` + unlink -> `stage_bytes` + `link_fd_no_clobber`, no-replace preserved.
     TRIAGED, NOT CHANGED — `scripts/arc_chart.py:157-172`: stages an `O_EXCL` uuid name relative to a bound `dir_fd` inside a session-owned directory, so there is no shared name another writer can swap. Recorded as a decision, and the packet states it rather than omitting it.
     HARNESSES RE-POINTED TO THE NEW PRIMITIVES: `tests/test_t1_batch_proof.py` `37543068d6c8…` **28/28** (its mutant disables the descriptor publisher), `tests/test_t1_pass10_repairs.py` `9ae611aee1d2…` **24/24** (T1-30's injected fault now targets `_publish_fd_no_replace`).
     GATES: `tests/run.sh` **rc=0** (all retained harnesses PASS), `./sanity.sh` **rc=0** with a live render; `test_a7_pass10_repairs` 49/49, `test_prove8` 34/34, `test_packet_a7_reporting` 30/30.
     PACKET `/tmp/cb-A7-pass19.txt` **101,790 B** sha256 `b1ad7fa081324d5ac9c12be8572d63fc611eb9a59cbd220838148fad23da0030`, **5/5 bindings re-hashed, drifted none**, DELEGATED to surf.
     RECORDS: 5 rows created/re-pointed; plan gained a `NAMEPUB` group (rows deduplicated so the per-group blocking sum cannot double-count a path already in B4/T1); plan Markdown twin matched; `_meta.groups_requiring_receipt` includes NAMEPUB; every manifest row now carries `origin_main_sha256`; matrix and doc-checker re-pinned.
     DOC **LANDED `298cbd8a8b9a…`**; identities re-recorded `8a1f219a…`; board **PASS (11 guards)**.
     Verification: binding re-hash -> 5/5 none drifted; `bash tests/run.sh` -> rc=0; `./sanity.sh` -> rc=0; `board-sweep.sh` -> PASS (11 guards).

123. [x] FOLDED INTO 133 — the pass-19 packet (b1ad7fa0) is one of the four live packets tracked there; keeping a separate awaiting line for it invited the same drift the delegation record just had.
124. [x] Deterministic gate built for the publish-by-name class — and its first run found four sites the audits missed.
     ARTIFACT: `tests/check_publish_by_name.py` (sha256 `4d5cf0d1…` recorded below), scanning `scripts/*.py` for
     `os.link(<name>, …)`, `os.replace(<name>, …)` and `fs_ops.link_no_clobber(<name>, …)`, with a reasoned ALLOW list
     (`fs_ops.py` owns the primitives; `arc_chart.py` = O_EXCL uuid under a bound `dir_fd`; `lora_pipeline.py` = training artifacts).
     SELF-TEST (`--self-test`): the scanner must flag a synthetic `os.link(staged, dest)` and must accept
     `link_fd_no_clobber(fd, dest)` — **rc=0**, so a scanner that silently finds nothing cannot pass as a green gate.
     FIRST REAL RUN (rc=1, four findings, none of which either hand audit had looked at):
     - `interrupt_sfx.py:369` `fs_ops.link_no_clobber(tomb, out)` — ROLLBACK restore;
     - `spyke_render.py:194` `fs_ops.link_no_clobber(bak, dest)` — ROLLBACK restore;
     - `spyke_render.py:248` `fs_ops.link_no_clobber(tomb, dest)` — ROLLBACK restore;
     - `spyke_render.py:604` `os.replace(dest, bak)` — moving the current artifact ASIDE.
     These are revert-path writes, not new publications, so they were NOT silently folded into the ALLOW list to make the
     gate green: the checker keeps failing and the work is opened as its own item.
     Verification: `python3 tests/check_publish_by_name.py --self-test` -> rc=0; `python3 tests/check_publish_by_name.py`
     -> rc=1 with exactly those four lines.

125. [x] Four revert-path name-based writes converted to descriptor publication; the class is now gated mechanically.
     TRIGGER: the scanner from item 124, not an audit - it flagged interrupt_sfx.py:369 and spyke_render.py:194,248
     (parked-file restores via fs_ops.link_no_clobber(<name>, dest)) and spyke_render.py:604 (os.replace(dest, bak)).
     FIX - scripts/fs_ops.py 6e971f4a9df0 gained link_path_no_clobber_verified(src, dest), which opens the source with
     O_PATH and installs from the DESCRIPTOR, and move_aside_verified(src, dest), which links the descriptor to the
     backup, verifies the installed inode, then retires the source name by PARKING (never a blind unlink).
     Call sites: scripts/spyke_render.py 7535ac331079, scripts/interrupt_sfx.py 9e83068d8140.
     REAL DEFECT THE HARNESS CAUGHT: the first version opened with O_RDONLY, which BLOCKS on a FIFO; the SP-21
     bounded-child control failed rather than being quietly adjusted. O_PATH is the fix and the reason is in a comment.
     GATE WIRED: tests/check_publish_by_name.py cbf19b3c7187 is invoked by tests/run.sh 61aeeecb866b; its --self-test
     proves it flags a synthetic os.link(staged, dest) and accepts link_fd_no_clobber(fd, dest).
     HARNESSES MOVED WITH THE CODE: test_a7_pass10_repairs.py e237a49ac14d 49/49 (restore mutant and IS-27 no-op link
     now target the descriptor helper), test_prove8.py 1b64007137f1 34/34 (SP-16's interrupt and the A8-PROOF-01 mutant
     now fire at fs_ops.move_aside_verified; patching os.replace would never fire), test_packet_a7_reporting.py
     d19c3dd88563 30/30, test_t1_pass10_repairs 24/24, test_t1_batch_proof 28/28, test_t1_20_mutation_controls 11/11.
     GATES: tests/run.sh rc=0 with "PUBLISH_BY_NAME: clean" in its own output; ./sanity.sh rc=0 with a live render.
     PACKET /tmp/cb-A7-pass20.txt 167,442 B sha256 b3757e9bb0dd2e09d70980a3f37efde45e52f24cba55bd56ac8b3701718ef7a4,
     8/8 bindings re-hashed with zero drift, DELEGATED to surf with a corrected packet order.
     RECORDS: REVERT group added to plan JSON + Markdown twin (paths already tracked in A7/T1 inherit their packet so no
     path is double-counted), _meta.groups_requiring_receipt includes REVERT, every manifest row carries
     origin_main_sha256, matrix and doc-checker follow pass 20, identities re-recorded 920980a5.
     DOC LANDED ed99e1ad0473; board PASS (11 guards), parse-check matches guards.
     Verification: checker -> clean rc=0; binding re-hash -> 8/8 none drifted; tests/run.sh -> rc=0; sanity.sh -> rc=0.
126. [x] WITHDRAWN — A7 pass 20 is dead, not awaiting: 3 of its 8 bindings drifted (fs_ops, tests/run.sh, test_a7_pass10_repairs). Earlier drift checks: pass 18 rebuilt/hash 2579bbe6, pass 20 hash b3757e9b. Both are superseded by pass 22 (519eab28) and were never submitted.
127. [x] wav_guard pass-2 FAIL applied and WG-06/WG-07/WG-08 repaired, with the reviewer's exact inputs as controls.
     VERDICT APPLIED FIRST-CLASS: verdict-intake.py --group GUARDS-WAVGUARD --report /tmp/surf-cb-WG2/response.md
     --apply -> "APPLIED: 0 PASS, 1 FAIL (response.md)"; FAIL skills/chatterbox-speak/scripts/wav_guard.py 998b2cdfc9f7;
     manifest now 34,662 B sha256 24aaed8f22621eb67eb29d17ada73fcf091907dd18e98e950ef1e05f48813c11.
     Response sha256 c0bf6b9a9186428d03c524541f36d8c50df2c3e6f8f7a752168252840cb42df7, receipt submitted_to_chatgpt=True,
     sentinel WEBGPT_DONE:20261113T015810Z:bec97dc9; failed attempt preserved at /tmp/surf-cb-WG2.failed1.
     EACH FINDING REPRODUCED BEFORE THE FIX (not after):
     - WG-06 stereo (20000,-20000) x16000 measured ac_rms 0.6103, active_frac 1.0, verdict None -> a constant-DC pair
       read as a full-scale tone because interleaved channels were measured as one signal.
     - WG-07 [202,-202]*160 + [0]*1919 (2,239 frames) measured ac_rms 0.00252, active_frac 0.1667, verdict None ->
       both just over the floors (0.0025 / 0.15) because the trailing partial window was dropped.
     - WG-08 read_snapshot("/proc/self/mem") opened, passed S_ISREG, then raised a raw OSError(EIO).
     FIXES - scripts/wav_guard.py db2c5619d10a:
     - signal_health(samples, rate, channels=1) splits channels and judges the BEST channel, so per-channel DC is
       silent while one loud channel still counts; sfx_verify.py 112e8d326818 passes the validated channel count
       through the same gate (its path had the same defect).
     - windows now cover every sample (range(0, n, win)), including the partial tail.
     - read_snapshot refuses /proc, /sys and /dev by resolved path, refuses zero-size regular files, and wraps read
       errors as WavError instead of letting OSError escape.
     CONTROLS - tests/test_wg_pass2_repairs.py 0d7c323b0bc9, 9/9, wired into tests/run.sh 2c01cc881b9d:
     WG-06 refused; channel-ignoring mutant passes; a real 440 Hz stereo tone still passes (not a blanket refusal);
     WG-07 refused; tail-dropping mutant passes; WG-08 /proc/self/mem refused with WavError; the mutant that removes
     the pseudo-fs and size guards admits /proc/self/cmdline (so the guard is what stops it); production refuses that
     readable pseudo-file too; an ordinary file still reads.
     GATES: tests/run.sh rc=0 with all harnesses PASS and PUBLISH_BY_NAME: clean; sanity.sh rc=0 with a live render.
     PACKET /tmp/cb-wg-pass3.txt 68,838 B sha256 12332dc9c67497164f2b34e663f2378a641360d586cf21e619249cc348309e5a,
     4/4 bindings re-hashed with zero drift, DELEGATED to surf as the next submission.
     RECORDS: 4 rows re-pointed; GUARDS-WAVGUARD group = cb-wg-pass3 (4); plan JSON+MD, matrix provenance and the
     doc-checker follow pass 3; identities re-recorded da3dc201.
     DOC LANDED d58ede78ad9e; board PASS (11 guards), parse-check matches guards.
     Verification: checker unaffected; binding re-hash -> 4/4 none drifted; tests/run.sh -> rc=0; sanity.sh -> rc=0.
128. [x] FOLDED INTO 132 — duplicate awaiting entry for wav_guard pass 3 / A7 pass 22.
129. [x] fs_ops named-copy defect (A7 pass-17 review) fixed by content verification; pass 18 and pass 20 WITHDRAWN, pass 22 supersedes them.
     THE REVIEW, verbatim in substance: "SP-30 PARTIAL, spyke_render.py:481-489 and fs_ops.py:129-132. IS-28 PARTIAL,
     interrupt_sfx.py:458-467 and fs_ops.py:126-133. Descriptor staging does not protect the named copy that follows it."
     CONFIRMED BY READING THE CODE: replace_from_fd copied the descriptor's bytes into a NAMED payload inside the private
     0700 dir and then os.replace'd it, so a same-user writer could substitute that payload.
     WHY NOT JUST LINK THE DESCRIPTOR: tested, not assumed - an O_TMPFILE inode cannot be linked out via /proc (os.link
     returns EXDEV: Invalid cross-device link) and AT_EMPTY_PATH requires CAP_DAC_READ_SEARCH. The first attempt at a
     descriptor hardlink failed exactly this way.
     FIX - scripts/fs_ops.py 815baca02542: the payload's content is verified against the descriptor TWICE, hash(payload)
     == hash(fd) immediately before the replace and hash(dest) == hash(fd) after it; a substitution inside the replace
     raises instead of reporting success. The replaced file's inode is also still checked against the staged descriptor.
     LIMIT STATED IN THE PACKET AND THE CONTROL: prevention is impossible while a name is involved, so the guarantee is
     DETECTION AND REFUSAL, not atomic prevention. The owner may instead choose to refuse overwrite-by-replace entirely;
     that policy question is recorded, not silently decided.
     CONTROL - tests/test_a7_pass10_repairs.py 4bb01849863c, 51/51: A17-IS28 drives a substituting os.replace (same-user
     writer overwrites the payload, then replaces) and requires production to raise; the mutant that removes the
     installed-content check installs FOREIGN-PAYLOAD and reports success, so the guard is what stops it.
     GATES: tests/run.sh rc=0 (all harnesses PASS, PUBLISH_BY_NAME: clean), sanity.sh rc=0 with a live render.
     PACKET /tmp/cb-A7-pass22.txt 117,532 B sha256 519eab2804322886599a2edd42736995fc027d7540ae5cac068c49764f260983,
     4/4 bindings re-hashed with zero drift, DELEGATED to surf as the second submission after wg pass 3.
     SUPERSEDES: pass 18 (2579bbe6) and pass 20 (b3757e9b), both of which carry fs_ops unchanged and would fail the same
     way; both are held, not submitted, as surf was instructed.
     RECORDS: 4 rows re-pointed; A7 and REVERT matrix rows follow pass 22; plan JSON+MD synced; doc-checker expectation
     sets regenerated from the matrix instead of hand-maintained; identities re-recorded da3dc201.
     DOC LANDED 89895b7808f6; board PASS (11 guards).
     Verification: binding re-hash -> 4/4 none drifted; test_a7_pass10_repairs -> 51/51; tests/run.sh -> rc=0; sanity.sh
     -> rc=0; board-sweep.sh -> PASS.
130. [x] FOLDED INTO 132 — duplicate awaiting entry for wav_guard pass 3 / A7 pass 22.
131. [x] B4 rebuild at CURRENT bytes done as pass 5 - the stale-hash hazard is removed before submission.
     WHY A REBUILD WAS REQUIRED: /tmp/cb-B4-pass4.txt (e7e9c1e00132280e) was built before pass 19 replaced
     scripts/speak.py's publish path with stage_bytes + replace_from_fd, so one of its five bindings was stale.
     Submitting it would have failed the review on drifted bytes rather than on the code - a wasted transport window.
     PACKET /tmp/cb-B4-pass5.txt 136,995 B sha256 53186cca51e6ee3709d657dcdea6e26d477397c0a06bbcf87041949a34955620,
     5/5 bindings re-hashed against the working tree with zero drift:
       scripts/speak_core.py 342744057172, scripts/speak.py 376982581e14 (was 7c238086 in pass 4),
       scripts/arc_chart.py 17ccab9c1e3b, scripts/test_core_contract.py 2c5d2c43803b, tests/test_prove4.py 9d890e4a8d99.
     The packet states the supersession explicitly and records that nothing from pass 2 / B4a / B4b is applied
     (those bound older packets 09b0e220 and 18dcd308, and B4a/B4b predate hash-bound verdict lines).
     RECORDS: 5 rows re-pointed to pass 5; B4 and T1 matrix rows follow it; plan JSON+MD synced; doc-checker
     expectations regenerated from the matrix instead of hand-maintained; identities re-recorded da3dc201.
     ONE RECORD BUG FOUND AND FIXED: the matrix's generated_from.manifest_sha256 was computed BEFORE the manifest
     write, so it recorded a pre-write digest and the guard reported MATRIX_DRIFT; the manifest is now written first
     and hashed after (fc9313a1bae0 == fc9313a1bae0).
     DOC LANDED 1b243a0ed589; board PASS (11 guards).
     DELEGATED to surf with the hash and the full submit order (wg pass 3, A7 pass 22, then B4 pass 5), and with
     every withdrawn hash named so a stale packet cannot be submitted by accident.
     Verification: binding re-hash -> 5/5 none drifted; board-sweep.sh -> PASS (11 guards).

1
3
2
.
 
[
~
]
 
A
w
a
i
t
i
n
g
 
s
u
r
f
:
 
F
O
U
R
 
l
i
v
e
 
p
a
c
k
e
t
s
,
 
a
l
l
 
b
o
u
n
d
 
a
n
d
 
d
r
i
f
t
-
f
r
e
e
 
(
v
e
r
i
f
i
e
d
 
t
h
i
s
 
t
u
r
n
)
,
 
p
l
u
s
 
p
a
s
s
 
1
9
.


 
 
 
 
 
-
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
1
9
.
t
x
t
 
 
b
1
a
d
7
f
a
0
8
1
3
2
4
d
5
a
 
 
5
 
f
i
l
e
s
 
 
b
i
n
d
i
n
g
s
 
5
/
5
 
d
r
i
f
t
e
d
 
n
o
n
e


 
 
 
 
 
-
 
/
t
m
p
/
c
b
-
w
g
-
p
a
s
s
3
.
t
x
t
 
 
 
1
2
3
3
2
d
c
9
c
6
7
4
9
7
1
6
 
 
4
 
f
i
l
e
s
 
 
b
i
n
d
i
n
g
s
 
4
/
4
 
d
r
i
f
t
e
d
 
n
o
n
e
 
 
 
(
W
G
-
0
6
/
0
7
/
0
8
 
r
e
p
a
i
r
s
)


 
 
 
 
 
-
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
2
2
.
t
x
t
 
 
5
1
9
e
a
b
2
8
0
4
3
2
2
8
8
6
 
 
4
 
f
i
l
e
s
 
 
b
i
n
d
i
n
g
s
 
4
/
4
 
d
r
i
f
t
e
d
 
n
o
n
e
 
 
 
(
f
s
_
o
p
s
 
n
a
m
e
d
-
c
o
p
y
)


 
 
 
 
 
-
 
/
t
m
p
/
c
b
-
B
4
-
p
a
s
s
5
.
t
x
t
 
 
 
5
3
1
8
6
c
c
a
5
1
e
6
e
e
3
7
 
 
5
 
f
i
l
e
s
 
 
b
i
n
d
i
n
g
s
 
5
/
5
 
d
r
i
f
t
e
d
 
n
o
n
e
 
 
 
(
B
4
 
a
t
 
c
u
r
r
e
n
t
 
b
y
t
e
s
)


 
 
 
 
 
D
E
A
D
,
 
d
o
 
n
o
t
 
s
u
b
m
i
t
 
(
w
i
t
h
d
r
a
w
n
 
a
n
d
 
n
o
w
 
D
R
I
F
T
E
D
,
 
s
o
 
t
h
e
y
 
c
a
n
n
o
t
 
e
v
e
n
 
b
e
 
r
e
v
i
e
w
e
d
 
a
s
 
b
u
i
l
t
)
:


 
 
 
 
 
p
a
s
s
 
1
8
 
2
5
7
9
b
b
e
6
 
(
7
/
1
0
 
b
i
n
d
i
n
g
s
 
d
r
i
f
t
e
d
)
,
 
p
a
s
s
 
2
0
 
b
3
7
5
7
e
9
b
 
(
3
/
8
 
d
r
i
f
t
e
d
)
,
 
p
a
s
s
 
1
7
 
0
c
2
6
5
7
5
9
,
 
B
4
 
p
a
s
s
 
2


 
 
 
 
 
0
a
4
b
3
3
8
d
 
a
n
d
 
p
a
s
s
 
4
 
e
7
e
9
c
1
e
0
 
s
u
p
e
r
s
e
d
e
d
 
b
y
 
p
a
s
s
 
5
.


 
 
 
 
 
W
H
I
C
H
 
G
R
O
U
P
 
E
A
C
H
 
F
E
E
D
S
:
 
p
a
s
s
 
1
9
 
-
>
 
N
A
M
E
P
U
B
 
(
2
 
r
o
w
s
)
 
a
n
d
 
t
h
e
 
B
4
/
T
1
 
r
o
w
s
 
t
h
a
t
 
i
n
h
e
r
i
t
 
i
t
s
 
b
y
t
e
s
;
 
p
a
s
s
 
2
2
 
-
>
 
A
7
 
a
n
d


 
 
 
 
 
R
E
V
E
R
T
;
 
w
g
 
p
a
s
s
 
3
 
-
>
 
G
U
A
R
D
S
-
W
A
V
G
U
A
R
D
;
 
B
4
 
p
a
s
s
 
5
 
-
>
 
B
4
 
a
n
d
 
T
1
.


 
 
 
 
 
W
H
E
N
 
A
 
V
E
R
D
I
C
T
 
A
R
R
I
V
E
S
:
 
v
e
r
d
i
c
t
-
w
a
t
c
h
.
p
y
 
-
-
r
e
q
u
i
r
e
-
r
e
a
d
y
 
-
>
 
v
e
r
d
i
c
t
-
i
n
t
a
k
e
.
p
y
 
-
-
g
r
o
u
p
 
<
g
r
o
u
p
>
 
-
-
a
p
p
l
y
 
-
>


 
 
 
 
 
l
a
n
d
i
n
g
-
c
h
e
c
k
.
s
h
 
<
g
r
o
u
p
>
 
-
>
 
l
a
n
d
 
o
n
l
y
 
P
A
S
S
 
r
o
w
s
 
w
i
t
h
 
a
 
J
S
O
N
 
r
e
v
i
e
w
e
r
 
r
e
c
e
i
p
t
 
(
g
r
e
e
n
f
i
e
l
d
=
t
r
u
e
 
f
o
r
 
n
e
w
 
p
a
t
h
s
)
 
-
>


 
 
 
 
 
r
e
-
r
e
a
d
 
e
v
e
r
y
 
o
r
i
g
i
n
/
m
a
i
n
 
b
l
o
b
 
b
y
 
h
a
s
h
 
-
>
 
s
w
e
e
p
 
+
 
p
a
r
s
e
.
 
A
 
F
A
I
L
 
b
e
c
o
m
e
s
 
a
 
f
i
r
s
t
-
c
l
a
s
s
 
F
A
I
L
 
r
o
w
 
a
t
 
r
e
v
i
e
w
e
d
 
b
y
t
e
s
.


 
 
 
 
 
O
W
N
E
R
:
 
s
u
r
f
 
(
s
u
b
m
i
s
s
i
o
n
 
+
 
v
e
r
d
i
c
t
)
.

132. [x] Deterministic packet recorder built; the ad-hoc scripts that caused five of six record drifts are retired.
     ARTIFACT: /mnt/storage12tb/skills/chatterbox-speak/outputs/record-packet.py sha256 7f51b1cb1a89e1fc...(see below)
     WHAT IT DOES in one pass: manifest rows (previous_sha256 kept, reviewed fields cleared), plan JSON with ONE path per
     group (a path is removed from any other group, so per-group blocking rows cannot double-count), the plan Markdown
     twin regenerated for EVERY group, delegations, then the matrix - with provenance computed from the bytes already on
     disk and written LAST. `--checker` re-derives the doc-checker's expectation sets from the matrix instead of leaving
     them hand-maintained.
     THREE BUGS IT FOUND IN ITSELF BEFORE IT WAS ACCEPTED (each one is a mistake I had made by hand):
     - a command naming `/tmp/receipt.json` fails `plan-receipt-step-check.py`, which requires
       `--reviewer-receipt /tmp/receipt-<slug>.json`; the tool now derives the name from the group.
     - rewriting only the target group's Markdown left another group's table stale (REVERT still listed `tests/run.sh`
       after it moved to GUARDS-WAVGUARD: "md table 4 != json 3"); the tool now rewrites every section.
     - hashing an artifact before writing it recorded a pre-write digest and produced MATRIX_DRIFT; provenance is now
       computed after every other write.
     ACCEPTANCE (measured, not asserted): two consecutive runs over the same packet are byte-identical on all five
     artifacts - manifest 641e4e7ac81cee4, plan JSON 2bd96bdbce5c9322, plan MD db263e54c51f2448, matrix ce81fc0f4e749186,
     delegations 4b7164b7f9b9931e - with rc=0 and `sweep: PASS (11 guards)` on both runs.
     SCOPE: it records a packet; it does not build or verify one. Packet construction stays explicit.
     Verification: `record-packet.py --packet /tmp/cb-wg-pass3.txt --group GUARDS-WAVGUARD --files ... --sweep` twice ->
     rc=0 both, identical hashes, sweep PASS (11 guards).

1
3
3
.
 
[
~
]
 
A
w
a
i
t
i
n
g
 
s
u
r
f
:
 
f
o
u
r
 
l
i
v
e
 
p
a
c
k
e
t
s
,
 
a
n
d
 
t
h
e
 
d
e
l
e
g
a
t
i
o
n
 
r
e
c
o
r
d
 
i
s
 
n
o
w
 
r
e
c
o
n
c
i
l
e
d
 
s
o
 
n
o
 
d
e
a
d
 
p
a
c
k
e
t
 
c
a
n
 
b
e
 
s
u
b
m
i
t
t
e
d
.


 
 
 
 
 
L
I
V
E
 
A
N
D
 
B
O
U
N
D
 
(
r
e
-
h
a
s
h
e
d
 
t
h
i
s
 
s
e
s
s
i
o
n
,
 
z
e
r
o
 
d
r
i
f
t
)
:


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
1
9
.
t
x
t
 
 
b
1
a
d
7
f
a
0
8
1
3
2
4
d
5
a
 
 
5
 
f
i
l
e
s
 
 
(
n
a
r
r
a
t
o
r
/
s
p
e
a
k
/
r
e
v
i
e
w
_
s
t
o
r
e
)


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
w
g
-
p
a
s
s
3
.
t
x
t
 
 
 
1
2
3
3
2
d
c
9
c
6
7
4
9
7
1
6
 
 
4
 
f
i
l
e
s
 
 
(
w
a
v
_
g
u
a
r
d
 
W
G
-
0
6
/
0
7
/
0
8
 
r
e
p
a
i
r
s
)


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
2
2
.
t
x
t
 
 
5
1
9
e
a
b
2
8
0
4
3
2
2
8
8
6
 
 
4
 
f
i
l
e
s
 
 
(
f
s
_
o
p
s
 
n
a
m
e
d
-
c
o
p
y
 
d
e
f
e
c
t
)


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
B
4
-
p
a
s
s
5
.
t
x
t
 
 
 
5
3
1
8
6
c
c
a
5
1
e
6
e
e
3
7
 
 
5
 
f
i
l
e
s
 
 
(
B
4
 
r
e
b
u
i
l
t
 
a
t
 
c
u
r
r
e
n
t
 
b
y
t
e
s
)


 
 
 
 
 
D
E
L
E
G
A
T
I
O
N
 
R
E
C
O
N
C
I
L
I
A
T
I
O
N
 
(
t
h
e
 
r
i
s
k
 
t
h
i
s
 
c
l
o
s
e
s
)
:
 
`
d
e
l
e
g
a
t
i
o
n
s
-
2
0
2
6
1
1
1
2
.
j
s
o
n
`
 
s
t
i
l
l
 
h
a
d
 
`
a
w
a
i
t
i
n
g
`
 
e
n
t
r
i
e
s


 
 
 
 
 
p
o
i
n
t
i
n
g
 
a
t
 
p
a
c
k
e
t
s
 
t
h
a
t
 
w
e
r
e
 
w
i
t
h
d
r
a
w
n
 
o
r
 
a
l
r
e
a
d
y
 
a
p
p
l
i
e
d
 
-
 
e
x
a
c
t
l
y
 
t
h
e
 
s
t
a
t
e
 
t
h
a
t
 
l
e
t
s
 
a
 
s
t
a
l
e
 
p
a
c
k
e
t
 
b
e


 
 
 
 
 
s
u
b
m
i
t
t
e
d
.
 
2
7
 
a
w
a
i
t
i
n
g
 
r
o
w
s
 
-
>
 
1
7
,
 
a
l
l
 
f
o
u
r
 
l
i
v
e
 
p
a
c
k
e
t
s
,
 
e
v
e
r
y
 
r
e
f
e
r
e
n
c
e
d
 
p
a
c
k
e
t
 
f
i
l
e
 
p
r
e
s
e
n
t
:


 
 
 
 
 
 
 
p
a
s
s
 
1
9
 
=
 
4
 
r
o
w
s
,
 
w
g
 
p
a
s
s
 
3
 
=
 
4
,
 
p
a
s
s
 
2
2
 
=
 
4
,
 
B
4
 
p
a
s
s
 
5
 
=
 
5
.


 
 
 
 
 
1
0
 
s
t
a
l
e
 
p
o
i
n
t
e
r
s
 
d
r
o
p
p
e
d
,
 
8
 
p
a
c
k
e
t
s
 
r
e
c
o
r
d
e
d
 
u
n
d
e
r
 
`
w
i
t
h
d
r
a
w
n
_
p
a
c
k
e
t
s
`
 
w
i
t
h
 
t
h
e
 
R
E
A
S
O
N
 
e
a
c
h
 
i
s
 
d
e
a
d


 
 
 
 
 
(
p
a
s
s
 
1
7
 
n
e
v
e
r
 
d
e
l
i
v
e
r
e
d
/
i
n
c
o
m
p
l
e
t
e
;
 
p
a
s
s
 
1
8
 
d
r
i
f
t
e
d
 
7
/
1
0
 
a
f
t
e
r
 
p
a
s
s
 
2
2
;
 
p
a
s
s
 
2
0
 
d
r
i
f
t
e
d
 
3
/
8
;
 
p
a
s
s
 
1
6
 
a
n
d


 
 
 
 
 
T
1
 
p
a
s
s
 
1
7
 
v
e
r
d
i
c
t
s
 
a
l
r
e
a
d
y
 
a
p
p
l
i
e
d
;
 
B
4
 
p
a
s
s
 
2
 
u
n
b
i
n
d
a
b
l
e
;
 
B
4
 
p
a
s
s
 
4
 
s
u
p
e
r
s
e
d
e
d
 
b
y
 
p
a
s
s
 
5
)
.


 
 
 
 
 
B
o
a
r
d
 
a
f
t
e
r
 
t
h
e
 
r
e
c
o
n
c
i
l
i
a
t
i
o
n
:
 
P
A
S
S
 
(
1
1
 
g
u
a
r
d
s
)
.


 
 
 
 
 
W
H
E
N
 
A
 
V
E
R
D
I
C
T
 
A
R
R
I
V
E
S
:
 
v
e
r
d
i
c
t
-
w
a
t
c
h
.
p
y
 
-
-
r
e
q
u
i
r
e
-
r
e
a
d
y
 
-
>
 
v
e
r
d
i
c
t
-
i
n
t
a
k
e
.
p
y
 
-
-
g
r
o
u
p
 
<
g
r
o
u
p
>
 
-
-
a
p
p
l
y
 
-
>


 
 
 
 
 
l
a
n
d
i
n
g
-
c
h
e
c
k
.
s
h
 
<
g
r
o
u
p
>
 
-
>
 
l
a
n
d
 
o
n
l
y
 
P
A
S
S
 
r
o
w
s
 
w
i
t
h
 
a
 
J
S
O
N
 
r
e
v
i
e
w
e
r
 
r
e
c
e
i
p
t
 
(
g
r
e
e
n
f
i
e
l
d
=
t
r
u
e
 
f
o
r
 
n
e
w
 
p
a
t
h
s
)
 
-
>


 
 
 
 
 
r
e
-
r
e
a
d
 
e
v
e
r
y
 
o
r
i
g
i
n
/
m
a
i
n
 
b
l
o
b
 
b
y
 
h
a
s
h
 
-
>
 
s
w
e
e
p
 
+
 
p
a
r
s
e
.
 
A
 
F
A
I
L
 
b
e
c
o
m
e
s
 
a
 
f
i
r
s
t
-
c
l
a
s
s
 
F
A
I
L
 
r
o
w
 
a
t
 
t
h
e
 
r
e
v
i
e
w
e
d
 
b
y
t
e
s
.


 
 
 
 
 
O
W
N
E
R
:
 
s
u
r
f
 
(
s
u
b
m
i
s
s
i
o
n
 
+
 
v
e
r
d
i
c
t
)
.
1
3
3
.
 
[
~
]
 
A
w
a
i
t
i
n
g
 
s
u
r
f
 
v
e
r
d
i
c
t
s
.
 
T
h
r
e
e
 
p
a
c
k
e
t
s
 
a
r
e
 
l
i
v
e
 
a
n
d
 
b
o
u
n
d
;
 
n
o
t
h
i
n
g
 
h
e
r
e
 
i
s
 
b
l
o
c
k
e
d
 
o
n
 
m
e
.


 
 
 
 
 
L
I
V
E
 
(
r
e
-
h
a
s
h
e
d
 
a
g
a
i
n
s
t
 
t
h
e
 
t
r
e
e
,
 
z
e
r
o
 
d
r
i
f
t
,
 
a
s
 
r
e
c
o
r
d
e
d
 
i
n
 
d
e
l
e
g
a
t
i
o
n
s
-
2
0
2
6
1
1
1
2
.
j
s
o
n
)
:


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
2
7
.
t
x
t
 
 
4
8
5
1
b
6
6
a
8
6
f
8
c
b
0
7
 
 
1
0
 
f
i
l
e
s
 
 
(
a
d
v
e
r
s
a
r
i
a
l
 
s
e
t
:
 
f
s
_
o
p
s
,
 
s
t
e
r
e
o
 
m
e
a
s
u
r
e
m
e
n
t
,
 
w
a
v
_
g
u
a
r
d
,


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
b
o
t
h
 
n
e
w
 
h
a
r
n
e
s
s
e
s
,
 
t
e
s
t
s
/
r
u
n
.
s
h
)


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
A
7
-
p
a
s
s
1
9
.
t
x
t
 
 
b
1
a
d
7
f
a
0
8
1
3
2
4
d
5
a
 
 
 
5
 
f
i
l
e
s
 
 
(
n
a
r
r
a
t
o
r
/
s
p
e
a
k
/
r
e
v
i
e
w
_
s
t
o
r
e
)


 
 
 
 
 
 
 
/
t
m
p
/
c
b
-
B
4
-
p
a
s
s
5
.
t
x
t
 
 
 
5
3
1
8
6
c
c
a
5
1
e
6
e
e
3
7
 
 
 
5
 
f
i
l
e
s
 
 
(
B
4
 
r
e
b
u
i
l
t
 
a
t
 
c
u
r
r
e
n
t
 
b
y
t
e
s
)


 
 
 
 
 
W
I
T
H
D
R
A
W
N
,
 
w
i
t
h
 
a
 
r
e
a
s
o
n
 
e
a
c
h
 
i
n
 
`
w
i
t
h
d
r
a
w
n
_
p
a
c
k
e
t
s
`
:
 
A
7
 
1
7
/
1
8
/
2
0
/
2
2
/
2
3
/
2
4
/
2
5
/
2
6
,
 
w
a
v
_
g
u
a
r
d
 
p
a
s
s
 
2
/
3
,
 
B
4
 
p
a
s
s
 
2
/
4
.


 
 
 
 
 
2
5
 
a
n
d
 
2
6
 
d
i
e
d
 
f
o
r
 
t
h
e
 
s
a
m
e
 
h
o
n
e
s
t
 
r
e
a
s
o
n
 
-
 
a
 
n
e
w
 
h
a
r
n
e
s
s
 
m
o
v
e
d
 
t
e
s
t
s
/
r
u
n
.
s
h
 
-
 
w
h
i
c
h
 
i
s
 
w
h
y
 
p
a
s
s
 
2
7
 
i
s
 
f
i
n
a
l
 
a
n
d
 
I


 
 
 
 
 
h
a
v
e
 
s
t
o
p
p
e
d
 
t
o
u
c
h
i
n
g
 
t
h
e
s
e
 
f
i
l
e
s
 
w
h
i
l
e
 
t
h
e
 
r
e
v
i
e
w
 
i
s
 
i
n
 
f
l
i
g
h
t
.


 
 
 
 
 
A
 
r
e
s
p
o
n
s
e
 
t
h
a
t
 
d
o
e
s
 
n
o
t
 
q
u
o
t
e
 
t
h
e
 
h
a
s
h
 
a
b
o
v
e
 
i
s
 
S
T
A
L
E
_
R
E
S
P
O
N
S
E
_
S
U
P
E
R
S
E
D
E
D
,
 
n
o
t
 
a
 
v
e
r
d
i
c
t
;
 
a
 
F
A
I
L
 
l
a
n
d
s
 
a
s
 
a


 
 
 
 
 
f
i
r
s
t
-
c
l
a
s
s
 
F
A
I
L
 
r
o
w
 
a
t
 
t
h
e
 
r
e
v
i
e
w
e
d
 
b
y
t
e
s
 
a
n
d
 
b
e
c
o
m
e
s
 
a
 
r
e
p
a
i
r
 
i
t
e
m
,
 
n
e
v
e
r
 
a
 
s
i
l
e
n
t
 
p
a
s
s
.


 
 
 
 
 
W
H
E
N
 
A
 
V
E
R
D
I
C
T
 
A
R
R
I
V
E
S
:
 
v
e
r
d
i
c
t
-
w
a
t
c
h
.
p
y
 
-
-
r
e
q
u
i
r
e
-
r
e
a
d
y
 
-
>
 
v
e
r
d
i
c
t
-
i
n
t
a
k
e
.
p
y
 
-
-
g
r
o
u
p
 
<
g
r
o
u
p
>
 
-
-
a
p
p
l
y
 
-
>


 
 
 
 
 
l
a
n
d
i
n
g
-
c
h
e
c
k
.
s
h
 
<
g
r
o
u
p
>
 
-
>
 
l
a
n
d
 
o
n
l
y
 
P
A
S
S
 
r
o
w
s
 
w
i
t
h
 
a
 
J
S
O
N
 
r
e
v
i
e
w
e
r
 
r
e
c
e
i
p
t
 
(
g
r
e
e
n
f
i
e
l
d
=
t
r
u
e
 
f
o
r
 
n
e
w
 
p
a
t
h
s
)
 
-
>


 
 
 
 
 
r
e
-
r
e
a
d
 
e
v
e
r
y
 
o
r
i
g
i
n
/
m
a
i
n
 
b
l
o
b
 
b
y
 
h
a
s
h
 
-
>
 
s
w
e
e
p
 
+
 
p
a
r
s
e
.


 
 
 
 
 
O
W
N
E
R
:
 
s
u
r
f
 
(
s
u
b
m
i
s
s
i
o
n
 
+
 
v
e
r
d
i
c
t
)
.
133. [~] Awaiting surf verdicts. Three packets are live and bound; nothing here is blocked on me.
     LIVE (re-hashed against the tree, zero drift, as recorded in delegations-20261112.json):
       /tmp/cb-A7-pass27.txt  4851b66a86f8cb07  10 files  (adversarial set: fs_ops, stereo measurement, wav_guard,
                                                             both retained harnesses, tests/run.sh)
       /tmp/cb-A7-pass19.txt  b1ad7fa081324d5a   5 files  (narrator/speak/review_store)
       /tmp/cb-B4-pass5.txt   53186cca51e6ee37   5 files  (B4 rebuilt at current bytes)
     WITHDRAWN, each with a reason in `withdrawn_packets`: A7 17/18/20/22/23/24/25/26, wav_guard pass 2/3, B4 pass 2/4.
     25 and 26 died for the same honest reason - a new harness moved tests/run.sh - which is why pass 27 is final and I
     have stopped touching these files while the review is in flight.
     A response that does not quote the hash above is STALE_RESPONSE_SUPERSEDED, not a verdict; a FAIL lands as a
     first-class FAIL row at the reviewed bytes and becomes a repair item, never a silent pass.
     WHEN A VERDICT ARRIVES: verdict-watch.py --require-ready -> verdict-intake.py --group <group> --apply ->
     landing-check.sh <group> -> land only PASS rows with a JSON reviewer receipt (greenfield=true for new paths) ->
     re-read every origin/main blob by hash -> sweep + parse.
     RECORD NOTE: this item was deleted twice by my own "fold X into Y" edits (the fold consumed its target). Restored
     from the delegation file, and now covered by outputs/next-md-check.py, which FAILED on the damaged file - missing
     133 plus two dangling fold references - before this restoration.
     OWNER: surf (submission + verdict).

134. [x] The packet recorder now REFUSES a stale packet, proven against a doctored copy.
     WHY IT MATTERS: B4 pass 4 cost a full cycle because it was recorded and queued after pass 19 had already changed
     one of its five bindings - a reviewer would have failed on drifted bytes rather than on the code.
     CHANGE (record-packet.py): before writing anything it parses the packet's `  <path>  sha256 <hash>` bindings,
     compares each to the working tree, and lists files the packet does not bind. Any mismatch, or any requested file
     that is not bound, exits 2 with no writes.
     MEASURED PROOF (both directions):
     - DOCTORED packet: a copy of /tmp/cb-A7-pass19.txt with the `scripts/narrator_sfx_batch.py` binding zeroed ->
       "REFUSED: cb-STALE-probe.txt does not describe the working tree; nothing was written", naming the stale binding
       (packet 000000000000 != tree 87af44926aff), rc=2, and ALL FIVE artifacts byte-identical before and after.
     - LIVE packet: /tmp/cb-A7-pass19.txt -> "bindings verified: 5 claimed, 0 stale, 0 missing", recorded 5 rows, rc=0.
     So the check cannot pass by doing nothing: the refusal case must fail AND leave the artifacts untouched, and the
     live case must still record.
     Board after both runs: eleven guards PASS.
     Verification: rc=2 with the refusal text on the doctored packet; artifacts unchanged (cmp on all five);
     rc=0 and 5 rows on the live packet; `record-packet.py` sha256 d3... (see run log); board-sweep.sh -> PASS.

135. [x] Out-of-phase stereo measured as SILENCE in interrupt_sfx - found by testing, fixed, controlled, reissued as pass 24.
     HOW IT SURFACED: not from a review. After the wav_guard WG-06 fix made signal_health per-channel, I asked whether the
     same failure survives elsewhere and read interrupt_sfx.measure(): it downmixes interleaved stereo before measuring
     activity (the IS-14 workaround, so a constant tone would not read as variation). A DOWNMIX cancels out-of-phase
     stereo: L=+sine, R=-sine averages to zero.
     REPRODUCED BEFORE CHANGING ANYTHING: 16 kHz stereo, amplitude 8000, 0.5 s -> peak 0.0000, ac_rms 0.0000,
     active_frac 0.0. A loud clip measured as pure silence, i.e. refused as "no signal variation" - wav_guard's WG-06
     class from the opposite side.
     FIX (scripts/interrupt_sfx.py bf82dfdb370d, was 9e83068d8140): channels are measured separately with the shared
     _health and the clip is judged on its BEST channel, matching the guard's rule; the downmix survives only for the
     legacy rms/dc display fields. After the fix the same clip reads peak 0.2441, ac_rms 0.1726, active 1.000.
     DISCRIMINATION CHECKED, NOT ASSUMED: constant-DC stereo still reads peak 0.6104, ac_rms 0.0000, active 0.0, so the
     change accepts real sound without accepting DC.
     CONTROL (tests/test_wg_pass2_repairs.py 8ddc00a4d783, 12/12): WG-06b sound case, WG-06b DC case, and a MUTANT with
     the downmix restored that must read the loud clip as silence (ac_rms < 0.0025). A control that cannot fail proves
     nothing, so the mutant is the point.
     PACKET CONSOLIDATION: the fix made a second live A7 packet name interrupt_sfx at a new hash, which would ask the
     reviewer to judge one file at two hashes. Packets 22 and 23 are withdrawn and /tmp/cb-A7-pass24.txt
     (125,635 B, sha256 74f516c2897278d9b9531bbc52de22e9d6287ed74239a333a6d98f515a962f16,
     5 bindings, 0 stale) is the single live A7 set. Delegations now list pass 19, pass 24, wg pass 3, B4 pass 5 only.
     GATES: tests/run.sh rc=0 (all harnesses PASS, PUBLISH_BY_NAME: clean), sanity.sh rc=0 with a live render.
     DOC LANDED a7906460312e; identity baseline re-recorded deliberately (bfe7bcf1ffdd), not self-healed; board PASS.
     RECORDER NOTE: while recording this I hit two bugs in my own new record-packet.py refusal path - it indexed only
     requested files (KeyError on a claimed-but-unrequested binding) and it treated a multi-group packet as stale. The
     tree side is now computed for EVERY claimed path, and the refusal prints MISSING rather than crashing.
     Verification: measure() before/after on the same clip; 12/12 harness; run.sh rc=0; sanity rc=0; packet re-hash 5/5
     zero drift; board-sweep.sh -> PASS (11 guards).

136. [x] Same-class stereo audit closed: sfx_verify averaged channels and disagreed with its own gate; pass 25 is the one live set.
     THE QUESTION I ASKED instead of assuming one fix covered the class: wav_guard WG-06 and interrupt_sfx both failed
     because a DOWNMIX cancels out-of-phase stereo (L=+sine, R=-sine averages to zero). I grepped every measurement path
     and tested the survivors with the same fixture rather than reading them and moving on.
     DEFECT FOUND (scripts/sfx_verify.py 405054bb985e, was 112e8d326818): read_audio() did pcm.mean(axis=1) before
     features(). The clip that the function's OWN gate scored at ac_rms 0.1942 / active_frac 1.0 came out of its feature
     layer as peak 0.0 / rms 0.0 / zcr 0.0, and those features are gated - zcr_min, centroid_min, bursts_min - so a loud
     clip would have been failed as "zcr 0 < 700" while the health check called it sound. One function disagreeing with
     itself is worse than either answer alone.
     FIX: features are measured on the channel with the greatest energy, the same rule the shared guard uses. Measured
     after the fix on the identical clip: peak 0.27, rms 0.19, zcr 879, centroid 452.9. The clipping check still runs
     per channel BEFORE selection.
     DISCRIMINATION PRESERVED: constant-DC stereo still reads ac_rms 0.0000 / active 0.0, so the change accepts real
     sound without accepting DC.
     CONTROLS (tests/test_wg_pass2_repairs.py f863b4e7956e, 14/14): WG-06b sound/DC/mutant and WG-06c non-zero features
     plus a MUTANT with mean(axis=1) restored, which must collapse the features to zero. Each guard's mutant must fail
     the case, so a control cannot pass by doing nothing.
     ALSO AUDITED, NOT CHANGED, with the reason recorded: hum_render._f0 downmixes, but the hum pipeline renders mono
     (filler_gain sets 1 channel; hum_render writes 1 channel), so the cancellation path is unreachable there.
     PACKET CONSOLIDATION: three repairs touched overlapping files and each reissue left two packets naming one file at
     two hashes. /tmp/cb-A7-pass25.txt (189,596 B,
     sha256 8f94f23a7cba0658073680747bc8c4655ae0395b90b38fc5774a20fc3097aabc, 8 bindings, 0 stale) is the single live
     set; A7 pass 22/23/24 and wav_guard pass 3 are withdrawn and recorded as such in delegations.
     GATES: tests/run.sh rc=0 (all harnesses PASS, PUBLISH_BY_NAME: clean), sanity.sh rc=0 with a live render.
     DOC LANDED b3c1668b957c; identity baseline re-recorded deliberately (ad99f5c1cc1b), not self-healed; board PASS.
     Verification: read_audio features before/after on one clip; 14/14 harness; run.sh rc=0; sanity rc=0; packet re-hash
     8/8 zero drift; board-sweep.sh -> PASS (11 guards).

137. [x] Frozen-library regression is now a retained harness, and the recorder no longer creates rows the plan guard crashes on.
     WHY: `sfx_verify --all` proves only that TODAY's code passes. After the per-channel stereo fixes changed how clips are
     measured, the thing that needed proving was "no REAL clip's verdict moved", and a one-off run cannot answer that
     again tomorrow.
     ARTIFACT tests/test_sfx_library_regression.py c9f216028c21, wired into tests/run.sh b6f9bedaef39. It compares the
     current verifier against the FROZEN set (eval-freeze-v1.json, 74 clips): ids must match exactly, no clip may gain a
     mechanical failure, every clip must still hash to its frozen bytes (nothing re-rendered in place), every clip must
     still report event_identity UNVERIFIED, and a SILENT clip must be refused.
     MEASURED: 74/74 ids match, 0 mechanical failures, 0 hash mismatches, 4 identity fields all UNVERIFIED, silent clip
     refused -> 5/5 in ~9 s. The mutation control is the point: without it the harness could pass by testing nothing.
     TWO OF MY OWN DEFECTS SURFACED WHILE WIRING IT, both fixed rather than worked around:
     - the control's manifest used a `clips` key where the schema requires `entries`, so the verifier refused before
       measuring and the control would have "passed" for the wrong reason;
     - my helper treated the verifier's rc=1 VERDICT as a crash (only rc>=2 is untrustworthy).
     RECORDER DEFECT FIXED AT THE SOURCE: new manifest rows omitted `origin_main_sha256`, which makes
     landing-plan-vs-manifest.py raise KeyError (a known trap). record-packet.py now always writes that field as an
     explicit null ("not on origin yet") and the one existing row was backfilled; board returned to PASS.
     PACKET: pass 25 was withdrawn the moment the new harness moved tests/run.sh, because a packet that binds a hash the
     tree no longer has is unreviewable. /tmp/cb-A7-pass26.txt (194,871 B,
     sha256 daebf5fc912036f01c787d9cfebf137866d6b0952364c3a993c9cd87a631f6f3, 9 bindings, 0 stale) is the single live set.
     Live awaiting packets now: ['cb-A7-pass19.txt', 'cb-A7-pass26.txt', 'cb-B4-pass5.txt'].
     GATES: tests/run.sh rc=0 (all harnesses PASS, PUBLISH_BY_NAME: clean), sanity.sh rc=0 with a live render.
     DOC LANDED 585ed9ce5c6a; board PASS (11 guards).
     Verification: regression harness 5/5; run.sh rc=0; sanity rc=0; packet re-hash 9/9 zero drift.

138. [x] The packet recorder's guarantees are now under a gate, not in a chat transcript.
     WHAT WAS MISSING: record-packet.py writes every packet record, but its two properties - a stale packet is REFUSED
     with no writes, and a second run changes nothing - had only been demonstrated by ad-hoc runs this session. Those are
     precisely the properties that failed by hand five times, so a proof that lives in a transcript is not a guard.
     ENABLER: the recorder gained `--out-dir`, so a harness can exercise it against a scratch artifact set without
     touching live records. Before that, the only way to test it was to mutate the real manifest.
     ARTIFACT tests/test_record_packet.py eb5a9c37ce33, wired into tests/run.sh fa6f9177a687. Seven checks, each
     measured against a temp artifact set seeded with the real schemas:
     - a packet matching the tree records rc=0, and the row carries the tree hash;
     - a new row carries `origin_main_sha256` explicitly (the field landing-plan-vs-manifest.py indexes, whose absence
       was a KeyError in this very session);
     - a second run is a no-op: rc=0 and all five artifacts BYTE-IDENTICAL;
     - a stale packet is REFUSED with rc=2, the stale binding is named, and NOTHING is written (before/after snapshots);
     - MUTATION CONTROL: with `if stale or missing:` replaced by `if False:`, the SAME stale packet is accepted - so the
       refusal is caused by that check and not by something incidental. 7/7.
     PACKET REISSUE, and why it was unavoidable: wiring the harness moved `tests/run.sh`, so pass 26 stopped describing
     the tree. /tmp/cb-A7-pass27.txt 200,468 B sha256
     4851b66a86f8cb07f5c36b3810a6bf9f841f239b85863c7a4981b43c779f98b7, 10 bindings, 0 stale, 0 missing. Pass 26 is
     withdrawn in delegations with that reason recorded; pass 27 is the final set for these files and was delegated to
     surf with every superseded hash named.
     GATES: tests/run.sh rc=0 (all retained harnesses PASS, PUBLISH_BY_NAME: clean), sanity.sh rc=0 with a live render,
     board-sweep.sh -> PASS (11 guards), identity baseline unchanged (ad99f5c1cc1b).
     DOC LANDED 1e4795268fff4badabcf192797f31bb262c30a22 on origin/main.
     Verification: harness 7/7; run.sh rc=0; sanity rc=0; packet re-hash 10/10 zero drift; board PASS.

139. [x] FOLDED INTO 133 — same awaiting state, and two lines for one condition is exactly how the delegation record accumulated stale pointers. Live packets at fold time: ['cb-A7-pass19.txt', 'cb-A7-pass27.txt', 'cb-B4-pass5.txt'].

140. [x] The queue itself now has a structural guard - added after my own fold deleted its target TWICE.
     THE DEFECT: two separate "fold item X into item Y" edits removed item Y. Both times the queue still looked healthy
     by the parser I had been using (no open items, no duplicates) while a live awaiting item - the one tracking the
     three live packets - had vanished, and two other items pointed at a number that no longer existed. A parser that
     only counts open items cannot see this, which is why it happened twice.
     ARTIFACT /mnt/storage12tb/skills/chatterbox-speak/outputs/next-md-check.py, now the TWELFTH guard in
     board-sweep.sh. It checks: no missing numbers in 1..max, no duplicates, every "FOLDED INTO N" resolves to an item
     that exists and is not itself a fold, and every item line matches the documented `N. [ ]/[~]/[x]` shape.
     PROVEN IN BOTH DIRECTIONS, in this order:
     - run against the damaged file it FAILED with exactly the real damage: "missing item numbers: [133]",
       "item 123 folds into 133, which does NOT exist", "item 139 folds into 133, which does NOT exist"
       -> VERDICT: STRUCTURE_DEFECT, rc=1.
     - after restoring 133 from delegations-20261112.json (live packets pass 27 / pass 19 / B4 pass 5, withdrawn list,
       verdict procedure, plus the record note that it had been deleted twice): items=139 done=136 open=0
       in-progress=[11, 104, 133] -> VERDICT: OK, rc=0.
     - wired into the sweep: board-sweep.sh -> PASS (12 guards), with `PASS next-md-check.py OK` named on its own line.
     WHY A GUARD AND NOT A NOTE: this is the fourth time this session that a hand-maintained record drifted (matrix
     provenance ordering, plan duplicates, doc-checker expectations, and now a self-deleting fold). The pattern is that
     a rule I must remember to apply is not a rule; the queue structure is now checked every sweep.
     Verification: next-md-check.py rc=1 on the damaged file with the three real problems named; rc=0 after restoration;
     board-sweep.sh -> PASS (12 guards); queue parses with no duplicates and no missing numbers.

141. [x] NEXT.md itself was UNTRACKED - 6,017 lines and 140 evidence-bearing items living only on this disk. Now landed.
     HOW IT SURFACED: checking whether the queue was committed in the chatterbox repo, `git ls-files --error-unmatch
     NEXT.md` failed. `git check-ignore` said it was not ignored - it had simply never been added, which is the exact
     shape of the earlier `sparta_metrics.py` loss: an untracked file that a cleanup sweep can remove while every check
     still reports healthy.
     LANDED f45a6636fde4fccb21ebc168ce35e5c0156c4d42 on origin/main via gh-land with the single explicit path NEXT.md
     (not a repo-wide add; the working tree also carries unrelated dirt - docs/proofs/tone_calibration_matrix.json,
     .pi/, .tmp-tagfx/, voices/ - which was left alone).
     VERIFIED BY READ-BACK, not by the tool's own success line:
       `git show origin/main:NEXT.md | sha256sum` -> 0dab86f0680db175578ee61a8b2e075098ce4d2885d5db2c521223c7fb3dfb16
       local NEXT.md                           -> 0dab86f0680db175578ee61a8b2e075098ce4d2885d5db2c521223c7fb3dfb16
       `git show --stat f45a6636` -> NEXT.md | 6017 +++ ; 1 file changed, 6017 insertions(+)
     The local branch now reads "behind 1" because gh-land lands by plumbing; that divergence is expected steady state,
     not a blocker, and the content is proven identical above.
     WHY IT MATTERS BEYOND BOOKKEEPING: every verdict, every withdrawn packet hash, and every reason a packet is dead
     lived only in this file. Losing it would have left the three live packets (pass 27 / pass 19 / B4 pass 5)
     indistinguishable from the eleven withdrawn ones.
     Verification: origin blob hash == local hash (0dab86f0); commit f45a6636 exists on origin/main with one file and
     6017 insertions.

142. [x] Ear-review surface verified live against the freeze - and it surfaced that TWO OWNER VERDICTS WERE DESTROYED.
     SURFACE, measured this turn (not assumed from a previous turn):
       :8797 /api/clips -> 200, 74 clips
       ids match eval-freeze-v1.json exactly (74/74, missing [] extra []); per-category counts identical; every served
       sha256 equals its frozen sha256 (0 mismatches) - so the owner would be judging the FROZEN bytes, not a drifted copy
       :8018/health 200, :8799/health 200, :8798 200, :8801 200 (root paths 404 on 8018/8799 are expected; /health is 200)
       manifest: 74 awaiting_owner_verdict, 6 excluded_nonconforming, 3 culled_content_failed
     THE FINDING, quoted from the manifest itself rather than inferred: every entry's recovery_note reads "manifest was
     overwritten by an incomplete SV-17 guard during a guard proof; rebuilt from the library WAVs plus the last full
     verify report. Prior statuses (human_confirmed/superseded/generation_failed) were not recoverable and default to
     awaiting_owner_verdict."
     CONSEQUENCE: `sigh-weary` and `sigh-shaky` - the two clips the owner had already confirmed by ear - are back to
     `awaiting_owner_verdict` with `reviewed_at_utc = null`. The production manifest contains ZERO human_confirmed rows.
     No production artifact anywhere in outputs/ holds those two verdicts; the only post-verdict manifest found was
     /tmp/rv-test (the ISOLATED item-118 proof), which is not production evidence.
     WHY THIS MATTERS MORE THAN THE SURFACE CHECK: a GUARD PROOF wrote to the PRODUCTION manifest. That is the failure
     mode where the tool that exists to protect data destroys it, and it has already cost the owner two listening
     verdicts. The surface being up is the smaller half of this item.
     Verification: curl /api/clips -> 74 clips, freeze id/category/sha256 cross-check 0 mismatches; /health 200 on 8018 and
     8799; manifest statuses counted 74/6/3; recovery_note quoted verbatim; sigh-weary/sigh-shaky reviewed_at_utc null.

143. [x] SV-17 guard proof can no longer write the production manifest (proven, and now a standing guard); the two lost verdicts are unrecoverable locally and are re-earned by the owner's single listening pass.
     HAZARD, measured against the LIVE manifest with three alias forms, all refused with rc=2:
     - `--out <production manifest>` -> "refusing to overwrite it";
     - `--out` a SAME-FILESYSTEM hardlink to it (inode 303105262 on both names) -> "is a link to manifest.json";
     - the recurrence case: `--manifest` points elsewhere while `--out` still names the library manifest -> refused.
     The manifest is BYTE-IDENTICAL afterwards: sha256 2b0897083f26cfa6bdb6e4d64387f8784915698c718e95cd0a82792b2c021d25,
     70,752 B (not merely "unchanged" - it matches the recorded value from before this work).
     RETAINED, not remembered: outputs/sv17-production-guard.py is now the THIRTEENTH sweep guard and re-runs all three
     probes plus the byte-identical assertion every sweep (board-sweep.sh -> PASS (13 guards), ~3.2 s).
     A CHECKER THAT CANNOT FAIL PROVES NOTHING: `--self-test` runs the identical probes against a stub verifier that
     exits 0 and writes nothing, and the guard reports that acceptance -> rc=0. So the refusal verdicts above are caused
     by the production guard, not by the probe setup.
     ONE OF MY OWN PROBES WAS INVALID FIRST AND IS RECORDED AS SUCH: I created the hardlink in /tmp, `ln` failed EXDEV,
     `--out` therefore named a path that did not exist, and rc=0 "proved" the alias was accepted. The probe was rebuilt on
     the manifest's own filesystem. A passing result for the wrong reason is how a guard quietly stops existing.
     RECOVERY IS NOT POSSIBLE FROM LOCAL STATE, and I checked rather than assumed: the library manifest has ZERO
     human_confirmed rows; sfx-library/fused-hmm/manifest.json has none; no review-event ledger mentions either id. The
     only post-verdict manifest on disk is /tmp/rv-test (the isolated item-118 proof), which is not production evidence.
     Both `sigh-weary` and `sigh-shaky` ARE in the frozen 74 (eval-freeze-v1.json), so the owner's single pass over the
     74 re-earns them at :8797 - no separate task, and no `human_confirmed` row fabricated from a machine PASS.
     DOC LANDED 95c005142ed64e431f07235b9bb686906622ed5b, which quotes the manifest's own recovery_note as the evidence of
     loss rather than paraphrasing it.
     Verification: three refusals rc=2; manifest sha256 2b0897083f26 == pre-work value; guard --self-test flags the stub;
     board-sweep.sh -> PASS (13 guards); origin doc blob == local doc blob.

144. [x] End-to-end product proof after the repair wave: /render speaks for all three speakers and every receipt binds the text.
     WHY THIS CHECK: the last items changed wav_guard, sfx_verify and interrupt_sfx - the code that decides whether audio is
     audible and whether a cue may be spliced. Everything so far proved those functions in isolation or against the frozen
     library; none proved the PRODUCT still renders speech through the live service after those edits.
     EVIDENCE per speaker (POST :8799/render, HTTP 200, then the ARTIFACT read back with wav_guard - the status alone is
     never treated as proof):
     - alex  -> wav /mnt/storage12tb/embry-voice/turns/spyke_alex_e2e-144_1.wav, voice=alex, 5.00 s, frames 120000 @24 kHz
                mono PCM16, measured ac_rms 0.0384, active_frac 0.636, sustained_problem None
     - jordan -> voice=jordan, 2.60 s, ac_rms 0.0551, active_frac 0.738, sha_ok True, text_ok True, no problem
     - spyke  -> voice=embry (the SPEAKER_VOICE mapping, not "spyke"), 2.68 s, ac_rms 0.0526, active_frac 0.806, no problem
     BINDING PROVEN BOTH WAYS on the alex call: sha256(wav bytes) == receipt.audio_sha256 (ec5d855c3b5b), and
     sha256(the EXACT text sent, including the [chuckle] tag) == receipt.text_sha256 (7b080aacf2d7). So the receipt
     describes the bytes on disk and the words actually requested, not a re-serialization.
     SCOPE STATED HONESTLY: this proves the speech path. It does NOT prove cue splicing - the receipt carries no cue field,
     and interruption SFX live in interrupt_sfx, which is proven by its own harnesses (MIN_S/MAX_S, MAX_PEAK, IS-28),
     not by /render. The [chuckle] tag was accepted (text bound) and did not produce a spliced cue on this path.
     ONE WRONG-TURN RECORDED: my first probe posted to :8798 and got HTTP 501 "Unsupported method ('POST')" - 8798 serves
     turns/audio over a plain HTTP server; /render is :8799. The 501 was read rather than reported as a product failure.
     Verification: three renders HTTP 200; each WAV re-read and measured; alex receipt sha matches the file; text sha
     matches the exact sent string; voices alex/jordan/embry distinct.

145. [x] An approved singular tag is NOT inert on the speech path - measured, with the decision rule declared before the run.
     WHAT WAS OBSERVABLE FIRST (7 renders): every tag case carried `requested_tone=None` and `normalized_tone=neutral_warm`,
     so on the TONE channel the tag does nothing at all. Durations did differ, but one render per tag cannot separate a tag
     effect from sampling noise - render is stochastic, so "different sha" proves only that it re-rendered.
     PRE-DECLARED RULE (written before the A/B run): 6 renders per arm, alternating; call an effect on duration only if the
     arms are FULLY SEPARATED (min tag > max control) or exact Mann-Whitney p < 0.05; otherwise record "no measurable
     effect". This is the step that stops a plausible-looking spread from being reported as a finding.
     RESULT (12 renders, alternating, same text, same speaker alex, same thread with a unique seq each so media names stay
     immutable):
       control  n=6 median 2.56 s  min 2.44  max 2.80   [2.44, 2.44, 2.52, 2.60, 2.64, 2.80]
       [sigh]   n=6 median 2.88 s  min 2.68  max 3.08   [2.68, 2.80, 2.84, 2.92, 3.00, 3.08]
       fully separated: False (control max 2.80 == a sigh sample); exact two-sided p computed from the U distribution with
       average ranks for ties = 0.0043 (< 0.05) -> rule fires: MEASURABLE EFFECT on duration, ~+0.32 s median.
       active_frac also moves down: control median 0.746 (0.705-0.769) vs sigh median 0.668 (0.657-0.739).
       tone_effective across all 12 runs: ['neutral_warm'] only.
     SO THE ANSWER IS TWO-SIDED, WHICH IS THE USEFUL PART: the tag changes the AUDIO and does not change the TONE STATE.
     Anyone reading `tone_effective` to decide whether a tag "worked" would conclude it never works; the duration and
     activity evidence shows the engine does consume it.
     NOT SPOKEN LITERALLY: local faster-whisper (base.en, CPU) on the tag renders returned clean speech with no "sigh",
     "chuckle" or "gasp" word in any transcript, so the tag is rendered as material, not read aloud as text.
     CONTROL PROBLEM RECORDED: my first A/B attempt reused seq=1 for every case and three cases returned HTTP 409
     "already exists; a re-cut needs a new seq" - the flat-media-name immutability rule, working as designed. The control
     render from that attempt was reused as the seq-1 control rather than re-rendered under a name that would collide.
     SCOPE: duration and activity are mechanical. Whether the inserted material IS a convincing sigh is the owner's ear,
     and event_identity remains UNVERIFIED.
     Verification: 12 renders HTTP 200, each WAV re-read and measured with wav_guard; exact U test p=0.0043; ASR clean on
     tag renders; receipt text_sha256 bound on every call.

146. [x] The tag's extra time is a PAUSE, not an event - and my first classifier was degenerate, so its verdicts are discarded.
     THE QUESTION: item 145 proved an approved tag changes the render (+0.32 s median). "Longer and less active" is equally
     consistent with an inserted nonverbal EVENT and with inserted SILENCE, and those are opposite outcomes for the product.
     INSTRUMENT 1, REJECTED AS DEGENERATE (recorded rather than quietly dropped): DTW alignment of tag vs control energy
     envelopes, classifying inserted spans by RMS against each clip's own silence floor. The floor came out at 0.0001, so
     "above the floor" was satisfied by noise: a span at 1.4% of speech RMS (0.0007) was labelled MATERIAL, and the
     alignment reported 6-8 "insertions" scattered MID-UTTERANCE for a tag that is a LEADING prefix. Those are artefacts
     of a stochastic take, not eight events. Reported here because a classifier that passes for the wrong reason is worse
     than no classifier - and because my pre-declared rule was too weak, not merely misapplied.
     INSTRUMENT 2, WHAT THE DATA ACTUALLY SUPPORTS. The tags are leading prefixes, so the decisive region is before speech
     onset, measured against control: control onset 0.07 s; sigh 0.15 s (+0.08); gasp 0.41 s (+0.34); chuckle 0.17 s
     (+0.10). The RMS of that pre-onset region is 0.0007 / 0.0007 / 0.0017 = 1.6% / 1.6% / 2.7% of speech RMS. That is
     SILENCE, not audible material, so by the declared rule (below the audible floor -> PAUSE) the verdict is PAUSE.
     WHERE THE REST OF THE TIME WENT (total deltas exceed onset deltas): sigh +0.40 s total vs +0.08 s lead, trail 0.23 s
     vs control 0.34 s; gasp +0.40 s total vs +0.34 s lead; chuckle +0.64 s total vs +0.10 s lead, and its LONGEST
     INTERNAL GAP grows from 0.33 s (control) to 0.54 s. So the tag lengthens the render by inserting/slackening SILENCE
     around and inside the line, not by adding a rendered sigh, gasp or chuckle.
     ANSWER TO THE NOW QUESTION: PAUSE. On this path the tag is a pacing change with no audible event; "delivery" would be
     an overclaim. This also explains item 145 cleanly: duration and activity move (silence does that) while
     tone_effective never leaves neutral_warm (nothing emotional is being rendered).
     SCOPE AND HONEST BOUNDARIES: one render per tag for the region classification (n=1); the duration effect itself is
     n=6 per arm from item 145. Leading-position tags only. Whether a MID-SENTENCE tag behaves differently is untested.
     Mechanical measurements only - whether a listener would hear a "hole" is the owner's ear, not this test.
     Verification: control onset 0.07 s, pre-onset RMS 1.6-2.7% of speech; chuckle longest internal gap 0.33 s -> 0.54 s;
     durations 2.66 / 3.06 / 3.06 / 3.30 s from the four requested renders (seq 20-23).

147. [x] The doc now says what is MEASURED about tags on /render, and the two code facts behind it are pinned.
     CODE FACTS, read from the paths rather than inferred from the skill text:
     - `/render` forwards `req.text` VERBATIM into `render_turn`, which posts `{"text": text, ...}` to the engine's
       `/synthesize` (render_service.py:169-170, spyke_render.py:519-525). It does not strip or rewrite tags.
     - `/render`'s OWN receipt has 24 keys and contains NEITHER `tag_handling` NOR `affect_effect` (verified on the
       item-144 call, not on a fresh assumption).
     - The ENGINE's `/synthesize` response DOES carry them: `tag_handling.tags_interpreted: true`,
       `applied_tags: ["[sigh]"]`, `tags_interpreted_reason: backend_chatterbox_turbo_consumes_event_tags_natively`,
       `unknown_tag_behavior: synthesized_as_literal_text`; `affect_effect.applied: false` with reason
       "affect_knobs_not_applied__render_kept_on_tag_consuming_backend_for_inline_event_tags"; `pace_effect.applied:
       false`, `reason: no_pace_requested`, input==output 2.96 s.
     - The fields the doc used to promise are populated on the CLI path only: speak.py:787 reads
       `service_json["tag_handling"].tags_interpreted`, speak_core.py:957 copies `tag_handling` into the receipt.
     SO THE OLD WORDING WAS HALF-TRUE AND THEREFORE MISLEADING: "the receipt's tag_handling / affect_effect fields record
     which side of that tradeoff you got" is true for the CLI receipt and FALSE for /render's, where the engine's own tag
     evidence is silently dropped.
     DOC CORRECTED (SKILL.md, landed 632c94f3c0774a15eb5e9be047143674e2e84092; origin blob sha256
     95bb0d32cad72105b344bece0c4784ffda2dcd0c0f6f5bd16678d3e8198ea5c3 == local): it now states the engine's
     tags_interpreted/applied_tags facts, scopes the receipt fields to the CLI path, and adds a measured paragraph: a
     leading singular tag adds ~0.3 s (median 2.56 -> 2.88 s, 6 renders/arm, exact p=0.0043), tone stays neutral_warm
     12/12, the added time is near-silence before onset (1.6-2.7 % of speech RMS) plus a longer internal gap, ASR hears no
     tag word, and `/render`'s receipt cannot show the engine's tag evidence. Conclusion stated plainly: a tag on this path
     is PACING, never delivered emotion; audible delivery comes from owner-confirmed SFX spliced at sentence boundaries.
     THIS IS A DOC FIX, NOT A BELIEF FIX: nothing was relaxed, no claim was invented to cover the gap, and the gap itself
     is opened as its own item below rather than buried in prose.
     Verification: 24-key /render receipt with no tag fields; engine response with tags_interpreted true; old wording quoted
     from SKILL.md:230-234 before the edit; landed commit 632c94f3 and origin blob == local (95bb0d32).

148. [x] /render now carries the engine's tag evidence and fails closed without it. (The pacing-only ACCEPTANCE question is opened separately below for the owner - it is not mine to answer.)
     THE GAP, read from the code rather than inferred: the engine's `/synthesize` response reports `tag_handling`
     (tags_interpreted true, applied_tags ["[sigh]"], accepted_tags, unknown_tag_behavior), `affect_effect` (applied
     false + reason) and `pace_effect`. `RenderReceipt` had fields for NONE of them and `render_turn` discarded them, so a
     /render caller could not distinguish "tag consumed" from "tag ignored" from "tag spoken as literal text".
     FIX, scripts/spyke_render.py 53d25500ba5f: a `_tag_evidence(text, svc)` helper copies the three fields VERBATIM from
     `svc.model_extra` (pydantic 2.12.3, verified with a live-shaped payload) and RAISES when the text contains a bracket
     tag but the response has no `tag_handling`. The three fields are added to `RenderReceipt` and populated in
     `render_turn`. The easier repair - emit an empty object - was REJECTED because it would read as "no tags" and hide
     exactly the loss the check exists to surface. No recomputation, no defaults that could imply a tag was applied.
     CONTROL, tests/test_render_tag_evidence.py 3a103286cf90, 7/7: tag evidence forwarded verbatim and applied_tags names
     the tag; a no-tag render records nothing and does not raise; tag text with no tag_handling raises with the field
     named; the receipt serializes all three; and a MUTATION CONTROL copies the module with the guard disabled
     (`if tag_handling is None and ...` -> `if False and ...`) and requires it to return None instead of raising - so the
     refusal is caused by the guard, not by the fixture.
     GATES: tests/run.sh 822a9ff3760d rc=0 with all retained harnesses PASS and `PUBLISH_BY_NAME: clean`; sanity.sh rc=0
     with a live render.
     PACKET /tmp/cb-A7-pass28.txt 207,474 B sha256
     bc186a7954d2c41a54000e6e1c2a6843a41b6d298cb37ac2cbb5738f0e5c2b14, 11 bindings re-hashed with zero drift, delegated
     to surf. Pass 27 is WITHDRAWN: `tests/run.sh` moved (fa6f9177 -> 822a9ff3) when the new harness was wired, so
     submitting it would have asked for a verdict on bytes the tree no longer has.
     RECORDS: doc landed edd89011ef0fb25a8a8c06fa55aa2ba9ca7a2f96; SKILL.md row re-pinned after its item-147 landing had
     left a LANDED_BLOB_MISMATCH; identity baseline re-recorded deliberately (6570ce304ec3); board PASS (13 guards).
     WHY THE FIELD GAP MATTERED ENOUGH TO FIX: item 146 measured a tag's real effect on /render as ~+0.32 s of near-
     silence (1.6-2.7 % of speech RMS, tone unchanged 12/12) while the engine simultaneously reported
     tags_interpreted=true. A receipt that hides the engine's own account of what it did with a tag is how a caller ends up
     believing tags deliver emotion.
     Verification: py_compile OK; helper exercised on tag/no-tag/fail-closed shapes before the harness was written; 7/7
     control with a live mutation; run.sh rc=0; sanity rc=0; packet re-hash 11/11 zero drift; board PASS.

149. [~] Awaiting OWNER DECISION (Graham): is PACING-ONLY acceptable behaviour for an inline tag on /render?
     WHAT IS MEASURED (items 145/146): a leading singular tag lengthens the render by ~0.32 s (median 2.56 -> 2.88 s, 6
     renders per arm, exact Mann-Whitney p = 0.0043), leaves `tone_effective` at neutral_warm in 12/12 runs, adds material
     that is near-silence before onset (1.6-2.7 % of speech RMS) plus a longer internal gap, and ASR hears no tag word. The
     engine concurrently reports tags_interpreted=true with the tag in applied_tags, and affect_effect.applied=false.
     THE TWO ANSWERS THIS NEEDS, and they lead to different work:
     (a) PACING IS FINE -> nothing more to build; the doc (item 147) already states it and audible emotion comes from
         owner-confirmed SFX spliced at sentence boundaries. This item closes.
     (b) A TAG SHOULD SOUND LIKE AN EVENT ON /render -> that is a SERVICE defect, not a doc problem: the fix belongs in
         the engine's tag realization, and it needs its own measurement (does the realized event rise above the silence
         floor?) rather than more receipt plumbing. The receipt work is already done either way.
     WHY I AM NOT DECIDING IT: acceptability is a product judgement about how Embry should sound, not a fact I can measure.
     Deciding it myself would be exactly the silent default this project keeps punishing.
     OWNER: Graham. Evidence ready at items 145, 146, 147 and 148; no further measurement is blocked on him.

