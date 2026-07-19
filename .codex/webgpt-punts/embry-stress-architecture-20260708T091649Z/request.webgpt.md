You are reviewing the Embry voice/chat stress-test architecture. Create an architecture/test-harness plan, not a polished diagram.

I attached the current evidence JSON bundle. Treat the attached JSON files as source evidence.

Goal:
Stress test Embry voice/chat system to identify concrete failures across RealtimeSTT ingress, speaker identity, memory/Tau routing, Chatterbox speech, Chat UX sync, orb sync, replay, and interruption.

Required invariant:
Every conversation test must include conversation arc, steering strategy, interruption strategy, tone selected through memory intent, and inline emotion tags. No flat/neutral tests.

Required proof style:
Non-mocked receipts; distinguish live/mocked; browser screenshots are not proof of service loop by themselves.

Chat UX requirement:
Voice and chat simultaneously, replay of actual sessions, turn lineage, memory reasoning trace dropdown, entity underlines from extract-entities, and Chatterbox audio.

Known evidence summary from attached files:
- Stress matrix has 300 sessions, 210 passed and 90 failed.
- Interruption, Chatterbox speech, replay, and orb sync have passing live audits for their current narrow proof slices.
- Memory/Tau routing is still failing around skill_call_receipt, Tau handoff, and Tau DAG receipts.
- Chat UX sync is still failing around assistant response plan to chat render lineage, turn id agreement, extract-entities linkage, and entity underline receipts.
- RealtimeSTT ingress is still failing around inconsistent browser/device ingress and factory capture rows.
- Speaker identity is still partial around source audio identity and physical speaker-to-mic identity gating.

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
