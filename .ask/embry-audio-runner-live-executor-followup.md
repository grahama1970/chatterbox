# Continue the Embry live-executor repair

Your previous response stopped after: "The failure is narrow: campaign state exists, but run never invokes components. I’m mapping each stalled stage to its existing owning callable."

Continue that work now. Return only:

1. The exact existing command or callable for each stage: managed RealtimeSTT arm/wait, speaker verification, Memory, persistent Tau tick, causal Chatterbox render, Jabra playback, Chat projection, orb projection, and replay.
2. The minimal `agent-skills` files to add or modify so `audio_e2e run` executes one real two-turn physical case.
3. Exact CLI arguments and receipt checks for that one case.
4. Any stage that cannot currently be composed, with the exact missing adapter.

Do not restate architecture, discuss future 200-case scaling, or create diagrams. End with the Surf-provided sentinel.
