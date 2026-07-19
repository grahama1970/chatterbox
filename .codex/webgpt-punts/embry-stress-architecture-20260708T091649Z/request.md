You are reviewing the Embry voice/chat stress-test architecture. Create an architecture/test-harness plan, not a polished diagram.

Context:
- Goal: Stress test Embry voice/chat system to identify concrete failures across RealtimeSTT ingress, speaker identity, memory/Tau routing, Chatterbox speech, Chat UX sync, orb sync, replay, and interruption.
- Current repo: /home/graham/workspace/experiments/chatterbox
- UX route under test: http://localhost:3002/#embry-voice
- Required invariant: every conversation test must include conversation arc, steering strategy, interruption strategy, tone selected through memory intent, and inline emotion tags. No flat/neutral tests.
- Required proof style: non-mocked receipts; distinguish live/mocked; browser screenshots are not proof of service loop by themselves.
- Chat UX needs voice and chat simultaneously, with replay of actual sessions, turn lineage, memory reasoning trace dropdown, entity underlines from extract-entities, and Chatterbox audio.

Current deterministic evidence:
1. Stress matrix
   - docs/EMBRY_STRESS_SESSION_MATRIX.json
   - 300 sessions total: 60 simple, 60 medium, 60 advanced, 60 adversarial, 60 soak.
   - Status counts: 210 passed, 90 failed.
   - Every row has conversation_requirements with:
     - flat_neutral_allowed=false
     - memory_intent_required=true
     - conversation_arc
     - steering_strategy
     - required_tone_family
     - inline_emotion_tags_required=true
     - minimum_inline_emotion_tag_count>=1
     - suggested_inline_emotion_tags
     - pause_strategy_required=true
     - interruption_strategy.required=true
     - interruption_strategy.natural_stop_required=true
     - spoken_text_schema_required=true
2. Tests now passing after updating stale expectations:
   - pytest -q tests/test_embry_stress_session_matrix.py tests/test_embry_goal_coverage_audit.py tests/test_embry_memory_tau_routing_evidence_audit.py tests/test_embry_chatterbox_speech_evidence_audit.py tests/test_embry_chat_ux_sync_evidence_audit.py tests/test_embry_realtimestt_ingress_evidence_audit.py tests/test_embry_speaker_identity_evidence_audit.py tests/test_embry_interruption_evidence_audit.py
   - Result: 88 passed in 0.25s.
3. Interruption audit:
   - docs/EMBRY_INTERRUPTION_EVIDENCE_AUDIT.json
   - status=passed, ok=true, live=true, mocked=false
   - Candidate receipt: /tmp/chatterbox-fork-agent-out/interruption-current/20260708T062448Z-rung4-live-horus-interrupt/rung4-live-interrupt.json
   - It includes ASR text, primary speaker verification, cancel/duck/stop, zero old-turn bytes after cancel, and new-turn-wins.
4. Chatterbox speech audit:
   - docs/EMBRY_CHATTERBOX_SPEECH_EVIDENCE_AUDIT.json
   - status=passed, ok=true, live=true, mocked=false
5. Replay audit:
   - docs/EMBRY_REPLAY_EVIDENCE_AUDIT.json
   - status=passed, ok=true, live=true, mocked=false
6. Orb sync audit:
   - docs/EMBRY_ORB_SYNC_EVIDENCE_AUDIT.json
   - status=passed, ok=true, live=true, mocked=false
7. Hard failing/partial areas:
   - docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json: status=failed, live=true, mocked=false. Failed gates: skill_call_receipt_missing, skill_tau_agent_handoff_missing, tau_dag_receipt_missing, tau_skill_gate:skill_call_receipt_not_emitted, tau_skill_gate:tau_agent_handoff_not_exercised, tau_skill_gate:tau_dag_receipt_not_created, tau_skill_routing_matrix_has_failures.
   - docs/EMBRY_CHAT_UX_SYNC_EVIDENCE_AUDIT.json: status=failed, live=true, mocked=false. Failed gates include assistant_response_plan_to_chat_render_lineage_missing, chat_render_receipt_v1_not_emitted, chat_turn_id_matches_response_plan_not_proven, extract_entities_receipt_not_linked, entity_underline_render_receipt_not_emitted, spoken_transcript_entity_underlines_not_proven.
   - docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json: status=failed, live=true, mocked=false. Failed gates include browser_device_ingress_inconsistent, current_factory_matrix_has_failures, asr_final_transcript_present, capture_captured_audio_rms, realtimestt_command_ok, realtimestt_receipt_ok, rung7_receipt_ok, speaker_memory_recall_found, speaker_resolution_known_horus.
   - docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json: status=failed, live=true, mocked=false. Failed gates: matrix_contains_source_audio_identity_unproven_rows, physical_speaker_to_microphone_identity_gating_not_proven.
8. Per-folder current stress matrix counts:
   - passed all 20: brave_research, persona_memory_miss, persona_memory_recall, skill_analytics, skill_create_evidence_case, skill_create_figure, skill_sparta_validator, sparta_qra_compliance, speaker_identity, tau_tool_orchestration.
   - chat_ux_sync: 4 passed, 16 failed.
   - factory_noise: 20 failed.
   - interruption: 20 failed in matrix despite separate current interruption audit passing one stronger rung.
   - tone_emotion: 5 passed, 15 failed.
   - voice_control_skill: 1 passed, 19 failed.

Question:
Create a source-derived numbered architecture/test-harness plan for the next 5-7 implementation/proof slices. For each slice include:
- exact subsystem boundary
- required endpoint or receipt schema
- what live command or browser/service action should produce the proof
- pass/fail gates
- how it should update the 300-session stress matrix
- what it must not claim

Prioritize resolving the high-value failures without drifting into dashboard/UI theater. Be blunt about whether Chat UX turn lineage or RealtimeSTT browser/device ingress should come first, and why.

Return only an actionable architecture/test-harness plan. Do not claim the system is complete.
