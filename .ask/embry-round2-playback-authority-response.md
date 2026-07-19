Architecture decision

Implement a one-shot Unix playback controller inside embry-voice-control. It should resolve the accepted artifact from the journal, preflight one explicit Jabra sink, run pw-play as a child process, observe the PipeWire graph, and append the three lifecycle events.

embry-voice-control
  -> resolve exact chatterbox.voice_render.completed
  -> verify WAV and sink
  -> append playback.requested
  -> execute pw-play --target <node.name>
  -> observe streaming node + active route to Jabra
  -> append playback.started
  -> wait for successful, plausible completion
  -> append playback.ended
  -> record separate human audible witness

This belongs in embry-voice-control because that component already owns session/turn identity, the SQLite journal, exact artifact resolution, claims, acknowledgements, and server-assigned event sequence allocation. The current artifact authority already resolves audio only through chatterbox.voice_render.completed and verifies its path, byte count, and SHA-256; the journal allocates sequences under an immediate SQLite transaction and treats an exact repeated event ID idempotently.

Do not put playback in:

Chatterbox: it ends at immutable audio rendering.

RealtimeSTT: it owns input.

UX Lab: it remains a read-only projection.

listener_service.py: that service should remain the journal API rather than hold a child audio process across a request.

The existing Round 1 projection deliberately exposes the artifact as audio_ready with playback_enabled=false; Round 2 should not change that UI contract.

1. Execution mechanism

Use pw-play directly:

pw-play --target <exact node.name> ...

Do not introduce PulseAudio compatibility, a new daemon, systemd user service, browser playback, or a custom PipeWire client for this rung.

pw-play already accepts PCM files supported by libsndfile, and its --target may be an object.serial or a node.name. PipeWire’s stream API specifically recommends selecting a target through target.object using node.name or object.serial, and describes raw node-ID targeting as deprecated. 
PipeWire
 
PipeWire

Use an explicit command equivalent to:

Bash
/usr/bin/pw-play \
  --verbose \
  --target "$SINK_NODE_NAME" \
  --latency 100ms \
  --volume 1.0 \
  --properties '{
    "application.id":"embry.voice.playback",
    "application.name":"Embry Voice Playback",
    "node.name":"embry.playback.<authority-short-id>",
    "media.name":"Embry listener-process-1",
    "media.role":"Communication",
    "node.dont-reconnect":"true"
  }' \
  "$JOURNAL_RESOLVED_AUDIO_PATH"

The controller must construct this as an argument list and invoke it without a shell.

--volume 1.0 is intentional. The observed Jabra sink volume of 0.70 is the sink volume; pw-play --volume is the stream’s own volume. Passing 0.70 to both would attenuate twice. The sink preflight should verify that object 64 is unmuted and currently near 0.70, while the child stream runs at unity. PipeWire documents --volume as stream volume, while wpctl get-volume ID reports the selected node’s volume and mute state. 
PipeWire
 
PipeWire

2. Sink authority
Required target

The controller must require:

--sink-node-name <exact PipeWire node.name>

There must be no default value and no fallback to:

auto
@DEFAULT_AUDIO_SINK@
64

At preflight, resolve exactly one PipeWire node with:

node.name        == supplied sink node name
media.class      == Audio/Sink
node.description == Jabra SPEAK 510 Analog Stereo
current object ID == 64       # observation for this live run only
muted            == false
volume           ~= 0.70

Also record, when present:

object.serial
device.id
device.name
device.serial
device.bus-id
device.product.name
device.api

pw-dump is appropriate for this because it emits the current PipeWire object state as JSON, including nodes, devices, ports, and links. 
PipeWire

Why sink 64 is not the authority

The number shown by wpctl status is the current PipeWire object ID. WirePlumber documents those status values as object IDs, and its default marker merely identifies which current node session policy would choose for automatic connections. 
PipeWire

That number may change when:

PipeWire restarts
WirePlumber restarts
the USB device reconnects
the device profile changes
nodes are recreated

It is also unsafe to assume that the displayed object ID 64 is the object.serial value accepted by pw-play --target. PipeWire defines object.serial as a separate number incremented whenever objects are created. 
PipeWire

Therefore:

64 = current-run cross-check
node.name = command target
device properties = hardware identity evidence

A node.name is more suitable than 64, but it is not immutable hardware identity either: it may vary with ALSA profile, USB topology, or configuration. That is why the receipt should preserve both the exact node.name and all available device identity properties.

3. Smallest defensible playback.started rule

Do not emit playback.started when subprocess.Popen() returns.

The smallest defensible rule with an unmodified pw-play binary is:

The child process is still alive.

pw-dump contains exactly one stream node whose:

node.name equals the unique stream name assigned by the controller;

protocol-supplied application.process.id equals the child PID;

stream state is running.

The exact selected Jabra sink node is still present under the same node.name.

The current graph contains an active directed link path from that stream node to the selected Jabra sink.

Conditions 1–4 appear in two consecutive graph snapshots, at least 20 ms apart.

Record the monotonic time of the first qualifying snapshot as started_monotonic_ns.

PipeWire exposes a distinct STREAMING state rather than treating “process exists” as stream activity, and pw-dump exposes current state as machine-readable JSON. 
PipeWire
 
PipeWire

This rule proves:

pw-play stream created
stream entered PipeWire streaming state
stream was actively routed to the selected Jabra sink

It does not prove that the first acoustic sample has physically left the speaker cone. That remaining gap is why the human audible witness is a separate required gate.

Graph matching

Set a unique deterministic stream name:

embry.playback.<first-16-hex-of-playback-authority>

Poll:

Bash
pw-dump --no-colors

every 20 ms with a 1,500 ms start timeout.

The parser should accept a direct active link or an active multi-node path if WirePlumber inserts a converter. It must not accept an active link to a different sink.

Persist both qualifying graph snapshots as JSON artifacts and hash them.

4. Controller lifecycle
Deterministic authority identity

Calculate:

Python
Run
authority_material = {
    "schema": "embry.pipewire_playback_authority_seed.v1",
    "session_id": session_id,
    "turn_id": turn_id,
    "render_event_id": render_event_id,
    "artifact_id": artifact_id,
    "audio_sha256": normalized_audio_sha256,
    "sink_node_name": sink_node_name,
}

Then:

authority_digest      = sha256(canonical_json(authority_material))
playback_authority_id = pipewire-playback:<first-24-hex>
idempotency_key       = sha256:<full-authority-digest>
stream_node_name      = embry.playback.<first-16-hex>
consumer_name         = embry-pipewire-playback:<first-24-hex>

The sink name is part of the key. Playing the same artifact to a different sink is a different request.

Before playback

The controller must:

Verify that the journal service at port 8032 reports the same SQLite path passed to the controller.

Locate the exact event:

chatterbox.voice_render.completed.ae1fa93d74f80c92

Require:

session_id == physical-hot-mic-20260711T010233Z-2668d0b9
turn_id == listener-process-1
type == chatterbox.voice_render.completed
live == true
mocked == false
causation_id == tau.turn_plan.completed.67d7b5460593b43d

Resolve the artifact through that event.

Recompute:

SHA-256;

file byte count;

WAV channels;

sample rate;

sample width;

frame count;

duration;

compression type.

Require:

artifact_id == audio:909a462d...
sha256      == 909a462d...
bytes       == 97998
channels    == 1
rate        == 24000
compression == PCM
duration    ~= 2040 ms

Verify the render event’s Tau-plan and TTS hashes.

Inspect the journal for prior events carrying this playback_authority_id.

Existing-run handling
Existing state	Controller action
No matching events	Continue
Complete requested → started → ended chain	Return existing receipt; spawn nothing
Existing playback.failed	Return prior failure; spawn nothing
requested without terminal event	Fail prior_playback_state_incomplete; spawn nothing
started without terminal event	Fail prior_playback_state_incomplete; spawn nothing
Conflicting events for the same authority ID	Fail playback_authority_conflict

Then claim the exact render event through the journal’s existing consumer claim mechanism. The journal supports exact-event claims with lineage checks, active leases, and already-acknowledged rejection; acknowledgements themselves are idempotent.

Lifecycle order
claim render event
append playback.requested
spawn pw-play
observe PipeWire graph
append playback.started
wait for pw-play
validate exit/timing/post-exit graph
append playback.ended
ack render event
write machine receipt
run internal duplicate probe

If anything fails after requested, append playback.failed and do not append ended.

5. Exact event contracts

All three events use:

schema=embry.voice_event.v1
session_id=physical-hot-mic-20260711T010233Z-2668d0b9
turn_id=listener-process-1
correlation_id=<correlation ID from the accepted render/source chain>
producer=embry-voice-control.pipewire-playback
live=true
mocked=false

The producer must never supply sequence; the journal assigns it transactionally.

playback.requested
JSON
{
  "schema": "embry.voice_event.v1",
  "event_id": "playback.requested.<deterministic-hex>",
  "session_id": "physical-hot-mic-20260711T010233Z-2668d0b9",
  "turn_id": "listener-process-1",
  "type": "playback.requested",
  "created_at": "<UTC wall-clock time>",
  "causation_id": "chatterbox.voice_render.completed.ae1fa93d74f80c92",
  "correlation_id": "<original correlation id>",
  "producer": "embry-voice-control.pipewire-playback",
  "live": true,
  "mocked": false,
  "artifact_hashes": {
    "audio_sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "tau_turn_plan_sha256": "sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca",
    "tts_render_text_sha256": "sha256:a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319"
  },
  "receipt_hash": "sha256:<canonical-payload-digest>",
  "payload": {
    "schema": "embry.playback_requested.v1",
    "playback_authority_id": "pipewire-playback:<24-hex>",
    "idempotency_key": "sha256:<authority-digest>",
    "render": {
      "event_id": "chatterbox.voice_render.completed.ae1fa93d74f80c92",
      "sequence": "<actual render sequence>",
      "tau_plan_event_id": "tau.turn_plan.completed.67d7b5460593b43d",
      "tau_turn_plan_sha256": "sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca",
      "tts_render_text_sha256": "sha256:a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319"
    },
    "artifact": {
      "artifact_id": "audio:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
      "path": "<journal-resolved path>",
      "sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
      "bytes": 97998,
      "container": "WAV",
      "encoding": "PCM_S16LE",
      "channels": 1,
      "sample_rate_hz": 24000,
      "frame_count": "<measured>",
      "duration_ms": "<measured>"
    },
    "sink": {
      "requested_node_name": "<exact Jabra node.name>",
      "object_id_at_preflight": 64,
      "object_serial_at_preflight": "<serial>",
      "node_description": "Jabra SPEAK 510 Analog Stereo",
      "media_class": "Audio/Sink",
      "device_id": "<device id>",
      "device_name": "<device name>",
      "device_serial": "<device serial or null>",
      "volume": 0.70,
      "muted": false,
      "selected_by_default_policy": false
    },
    "process": {
      "executable": "/usr/bin/pw-play",
      "version": "<pw-play --version>",
      "argv": ["<exact argv>"],
      "pid": null,
      "stream_node_name": "embry.playback.<16-hex>"
    },
    "clock": {
      "source": "CLOCK_MONOTONIC",
      "boot_id": "<Linux boot id>",
      "requested_monotonic_ns": 0
    }
  }
}

pid must be null in this event because it is emitted before process creation. A future PID must not be invented merely to satisfy schema symmetry.

playback.started
JSON
{
  "schema": "embry.voice_event.v1",
  "event_id": "playback.started.<deterministic-hex>",
  "session_id": "physical-hot-mic-20260711T010233Z-2668d0b9",
  "turn_id": "listener-process-1",
  "type": "playback.started",
  "created_at": "<UTC time of first qualifying graph observation>",
  "causation_id": "playback.requested.<hex>",
  "correlation_id": "<original correlation id>",
  "producer": "embry-voice-control.pipewire-playback",
  "live": true,
  "mocked": false,
  "artifact_hashes": {
    "audio_sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "pipewire_start_snapshot_sha256": "sha256:<snapshot digest>"
  },
  "receipt_hash": "sha256:<canonical-payload-digest>",
  "payload": {
    "schema": "embry.playback_started.v1",
    "playback_authority_id": "pipewire-playback:<24-hex>",
    "idempotency_key": "sha256:<authority-digest>",
    "artifact_id": "audio:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "audio_sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "render_event_id": "chatterbox.voice_render.completed.ae1fa93d74f80c92",
    "tau_turn_plan_sha256": "sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca",
    "process": {
      "pid": 12345,
      "alive_at_detection": true,
      "argv": ["<exact argv>"]
    },
    "sink": {
      "node_name": "<exact Jabra node.name>",
      "node_id_at_start": "<current id>",
      "node_description": "Jabra SPEAK 510 Analog Stereo"
    },
    "pipewire_graph": {
      "stream_node_name": "embry.playback.<16-hex>",
      "stream_node_id": "<id>",
      "stream_object_serial": "<serial>",
      "stream_state": "running",
      "target_object": "<exact Jabra node.name>",
      "active_link_path": ["<stream id>", "<optional converter ids>", "<sink id>"],
      "active_link_ids": ["<link ids>"],
      "qualifying_snapshot_count": 2,
      "snapshot_interval_ms": 20,
      "first_snapshot_path": "<path>",
      "first_snapshot_sha256": "sha256:<digest>",
      "confirming_snapshot_path": "<path>",
      "confirming_snapshot_sha256": "sha256:<digest>"
    },
    "clock": {
      "requested_monotonic_ns": 0,
      "started_monotonic_ns": 0,
      "requested_to_started_ms": 0
    }
  }
}
playback.ended
JSON
{
  "schema": "embry.voice_event.v1",
  "event_id": "playback.ended.<deterministic-hex>",
  "session_id": "physical-hot-mic-20260711T010233Z-2668d0b9",
  "turn_id": "listener-process-1",
  "type": "playback.ended",
  "created_at": "<UTC process-completion time>",
  "causation_id": "playback.started.<hex>",
  "correlation_id": "<original correlation id>",
  "producer": "embry-voice-control.pipewire-playback",
  "live": true,
  "mocked": false,
  "artifact_hashes": {
    "audio_sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "pipewire_end_snapshot_sha256": "sha256:<digest>",
    "pw_play_stdout_sha256": "sha256:<digest>",
    "pw_play_stderr_sha256": "sha256:<digest>"
  },
  "receipt_hash": "sha256:<canonical-payload-digest>",
  "payload": {
    "schema": "embry.playback_ended.v1",
    "playback_authority_id": "pipewire-playback:<24-hex>",
    "idempotency_key": "sha256:<authority-digest>",
    "artifact_id": "audio:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "audio_sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "render_event_id": "chatterbox.voice_render.completed.ae1fa93d74f80c92",
    "tau_turn_plan_sha256": "sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca",
    "process": {
      "pid": 12345,
      "exit_code": 0,
      "stdout_path": "<path>",
      "stdout_sha256": "sha256:<digest>",
      "stderr_path": "<path>",
      "stderr_sha256": "sha256:<digest>"
    },
    "sink": {
      "node_name": "<exact Jabra node.name>",
      "node_description": "Jabra SPEAK 510 Analog Stereo"
    },
    "clock": {
      "requested_monotonic_ns": 0,
      "started_monotonic_ns": 0,
      "ended_monotonic_ns": 0,
      "requested_to_started_ms": 0,
      "started_to_ended_ms": 0,
      "requested_to_ended_ms": 0
    },
    "timing_gate": {
      "expected_duration_ms": 2040,
      "minimum_requested_to_ended_ms": 1540,
      "maximum_requested_to_ended_ms": 5040,
      "minimum_started_to_ended_ms": 1040,
      "plausible": true
    },
    "post_exit_graph": {
      "stream_absent_or_not_running": true,
      "snapshot_path": "<path>",
      "snapshot_sha256": "sha256:<digest>"
    }
  }
}
6. Timing and terminal-state rules

Append playback.ended only when all are true:

playback.started was emitted
pw-play exit code == 0
requested_to_started <= 1500 ms
requested_to_ended >= duration - 500 ms
requested_to_ended <= duration + 3000 ms
started_to_ended >= max(250 ms, duration - 1000 ms)
stream is absent or no longer running after exit
audio file is still present with the same SHA-256

For the 2,040 ms file, that gives:

requested-to-ended: 1540–5040 ms
started-to-ended:   at least 1040 ms

If the child exits before start detection, exits nonzero, exceeds the timeout, loses its sink route, or fails timing plausibility:

append playback.failed
do not append playback.ended
do not acknowledge the render claim

playback.failed is diagnostic and does not satisfy Round 2.

7. Idempotency behavior

The controller must inspect journal state before spawning and claim the render event before appending requested.

A repeated invocation with the same deterministic key must return:

JSON
{
  "idempotent_replay": true,
  "process_spawned": false,
  "existing_requested_event_id": "...",
  "existing_started_event_id": "...",
  "existing_ended_event_id": "..."
}

The live proof command should include:

--duplicate-probe

After the first successful playback, the controller re-enters its preparation path with the same inputs and a process runner that is configured to fail if invoked. The probe passes only when no second Popen call occurs.

Do not silently retry a partially completed playback. Human hearing makes an uncertain prior attempt materially different from an ordinary idempotent API operation.

8. Machine and human receipts
Machine receipt

Write:

/tmp/embry-round2-pipewire-playback/machine-receipt.json
JSON
{
  "schema": "embry.voice.pipewire_playback_machine_receipt.v1",
  "status": "MACHINE_PASS_HUMAN_PENDING",
  "ok": true,
  "proof_complete": false,
  "live": true,
  "mocked": false,

  "session_id": "physical-hot-mic-20260711T010233Z-2668d0b9",
  "turn_id": "listener-process-1",
  "source_event_id": "listener.final_transcript.e05728f278813654",
  "render_event_id": "chatterbox.voice_render.completed.ae1fa93d74f80c92",
  "playback_authority_id": "pipewire-playback:<24-hex>",
  "idempotency_key": "sha256:<digest>",

  "artifact": {
    "artifact_id": "audio:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "sha256": "sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc",
    "bytes": 97998,
    "sample_rate_hz": 24000,
    "channels": 1,
    "duration_ms": 2040
  },

  "sink": {
    "node_name": "<exact node.name>",
    "object_id_at_preflight": 64,
    "description": "Jabra SPEAK 510 Analog Stereo",
    "volume": 0.70,
    "muted": false
  },

  "events": {
    "requested": {
      "event_id": "...",
      "sequence": 47
    },
    "started": {
      "event_id": "...",
      "sequence": 48
    },
    "ended": {
      "event_id": "...",
      "sequence": 49
    }
  },

  "machine_acceptance": {
    "artifact_resolved_only_from_render_event": true,
    "artifact_hash_verified_before_playback": true,
    "artifact_size_verified_before_playback": true,
    "wav_metadata_verified": true,
    "explicit_sink_node_name_used": true,
    "sink_unique_and_jabra": true,
    "sink_unmuted": true,
    "requested_event_preceded_process_spawn": true,
    "started_not_inferred_from_spawn": true,
    "stream_running_observed": true,
    "active_route_to_selected_sink_observed": true,
    "two_consecutive_start_snapshots": true,
    "process_exit_zero": true,
    "timing_plausible": true,
    "stream_stopped_after_exit": true,
    "journal_lineage_preserved": true,
    "render_claim_acknowledged": true,
    "duplicate_probe_spawn_count_zero": true,
    "browser_audio_not_used": true,
    "orb_events_emitted": false
  },

  "human_audible_witness": {
    "status": "pending",
    "expected_text": "The capital of France is Paris.",
    "expected_text_sha256": "sha256:a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319",
    "prompt": "Did you hear exactly \"The capital of France is Paris.\" from the Jabra SPEAK 510?"
  },

  "failed_gates": []
}

The event sequences above are illustrative; do not hard-code 47–49. Other producers may append session events concurrently.

Human witness procedure

After machine playback finishes, the project agent must ask:

Did you hear exactly “The capital of France is Paris.” through the Jabra SPEAK 510 during playback pipewire-playback:<id>? Reply EXACT, NOT_HEARD, or DIFFERENT: <what you heard>.

The project agent must not answer this question itself.

After an actual human response, preserve the response verbatim in:

/tmp/embry-round2-pipewire-playback/human-reply.txt

Then run:

Bash
SKILL_ROOT=/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control

uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$SKILL_ROOT/scripts/record_pipewire_playback_witness.py" \
  --machine-receipt /tmp/embry-round2-pipewire-playback/machine-receipt.json \
  --human-reply-file /tmp/embry-round2-pipewire-playback/human-reply.txt \
  --verdict heard_exactly \
  --output /tmp/embry-round2-pipewire-playback/receipt.json

Use --verdict not_heard or --verdict heard_different when appropriate.

The final receipt:

JSON
{
  "schema": "embry.voice.pipewire_playback_authority_receipt.v1",
  "status": "PASS",
  "ok": true,
  "live": true,
  "mocked": false,
  "machine_receipt": {
    "path": ".../machine-receipt.json",
    "sha256": "sha256:<digest>"
  },
  "human_audible_witness": {
    "status": "confirmed_exact",
    "source": "explicit_human_response",
    "response_path": ".../human-reply.txt",
    "response_sha256": "sha256:<digest>",
    "expected_text_sha256": "sha256:a1b7eb2e...",
    "heard_exactly": true,
    "recorded_at": "<UTC>"
  },
  "failed_gates": []
}

Until that human witness exists:

machine playback = passed
Round 2 gate = incomplete
9. Exact file ownership

Repository: grahama1970/agent-skills

Add:

skills/embry-voice-control/
├── src/embry_voice_control/
│   ├── pipewire_graph.py
│   ├── pipewire_playback.py
│   └── playback_receipts.py
├── scripts/
│   ├── prove_pipewire_playback.py
│   └── record_pipewire_playback_witness.py
├── schemas/
│   ├── embry.playback_requested.v1.schema.json
│   ├── embry.playback_started.v1.schema.json
│   ├── embry.playback_ended.v1.schema.json
│   ├── embry.voice.pipewire_playback_machine_receipt.v1.schema.json
│   └── embry.voice.pipewire_playback_authority_receipt.v1.schema.json
└── tests/
    ├── fixtures/pipewire/
    │   ├── jabra-idle.json
    │   ├── embry-stream-running-1.json
    │   ├── embry-stream-running-2.json
    │   ├── wrong-sink-running.json
    │   └── post-exit.json
    ├── test_pipewire_graph.py
    ├── test_pipewire_playback.py
    └── test_playback_witness.py

Modify narrowly:

src/embry_voice_control/artifact_authority.py
references/endpoint-contract.md
SKILL.md

Extend resolve_audio_artifact() with optional expected values:

Python
Run
render_event_id
artifact_id
audio_bytes
tau_turn_plan_sha256

Do not change:

grahama1970/chatterbox
grahama1970/RealtimeSTT
grahama1970/tau
grahama1970/graph-memory-operator
grahama1970/pi-mono
10. Focused deterministic tests
Artifact and lineage
exact render event resolves accepted audio
different render event rejected
wrong session rejected
wrong turn rejected
wrong artifact ID rejected
wrong audio hash rejected
wrong byte count rejected
wrong Tau-plan hash rejected
missing file rejected
WAV rate/channel/duration mismatch rejected
Sink selection
exact Jabra node.name accepted
zero matching sinks rejected
multiple matching sinks rejected
wrong media.class rejected
wrong description rejected
current ID 64 mapped to wrong node name rejected
default marker alone rejected
muted sink rejected
volume outside configured tolerance rejected
numeric 64 never appears after --target
Start detection
process spawn alone emits no started event
running stream without Jabra route rejected
active route with non-running stream rejected
one qualifying snapshot insufficient
two consecutive qualifying snapshots accepted
PID mismatch rejected
stream-name mismatch rejected
route changing sinks between snapshots rejected
process exiting during detection rejected
End detection
exit zero plus plausible timing emits ended
exit nonzero emits failed, not ended
too-short timing emits failed
timeout emits failed
stream still running after child exit emits failed
artifact changed during playback emits failed
Idempotency
same key while claim active spawns once
complete prior chain returns existing receipt and spawns zero times
partial prior chain fails and spawns zero times
conflicting event ID fails
exact repeated journal event is idempotent
Human witness
machine receipt alone cannot produce final PASS
EXACT plus verbatim response produces PASS
NOT_HEARD produces FAIL
DIFFERENT produces FAIL
missing response file rejected
response hash preserved

Run:

Bash
cd /home/graham/workspace/experiments/agent-skills

uv run --project skills/embry-voice-control --locked --no-sync \
  python -m pytest \
  skills/embry-voice-control/tests/test_pipewire_graph.py \
  skills/embry-voice-control/tests/test_pipewire_playback.py \
  skills/embry-voice-control/tests/test_playback_witness.py \
  -q
11. One live playback command

The shell block below uses object ID 64 only to resolve and cross-check the current Jabra node. The actual pw-play target is the resulting node.name.

Bash
set -euo pipefail

SKILL_ROOT=/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control
JOURNAL_DB=/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3
OUT=/tmp/embry-round2-pipewire-playback

rm -rf "$OUT"
mkdir -p "$OUT"

SINK_NODE_NAME="$(
  pw-dump --no-colors |
  jq -er '
    [
      .[]
      | select(.id == 64)
      | select(.type == "PipeWire:Interface:Node")
      | .info.props
      | select(.["media.class"] == "Audio/Sink")
      | select(
          (.["node.description"] // "")
          | test("^Jabra SPEAK 510 Analog Stereo$"; "i")
        )
      | .["node.name"]
    ]
    | if length == 1 and .[0] != null and .[0] != ""
      then .[0]
      else error("sink_64_is_not_one_unique_jabra_audio_sink")
      end
  '
)"

printf 'Selected explicit PipeWire target: %s\n' "$SINK_NODE_NAME"

uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$SKILL_ROOT/scripts/prove_pipewire_playback.py" \
  --journal-db "$JOURNAL_DB" \
  --journal-url http://127.0.0.1:8032 \
  --session-id physical-hot-mic-20260711T010233Z-2668d0b9 \
  --turn-id listener-process-1 \
  --source-event-id listener.final_transcript.e05728f278813654 \
  --source-sequence 29 \
  --tau-plan-event-id tau.turn_plan.completed.67d7b5460593b43d \
  --render-event-id chatterbox.voice_render.completed.ae1fa93d74f80c92 \
  --tau-plan-sha256 sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca \
  --tts-text-sha256 sha256:a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319 \
  --audio-sha256 sha256:909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc \
  --audio-bytes 97998 \
  --sink-node-name "$SINK_NODE_NAME" \
  --expected-current-node-id 64 \
  --expected-sink-description "Jabra SPEAK 510 Analog Stereo" \
  --expected-sink-volume 0.70 \
  --sink-volume-tolerance 0.02 \
  --pw-play /usr/bin/pw-play \
  --latency 100ms \
  --start-timeout-ms 1500 \
  --graph-poll-ms 20 \
  --start-confirmations 2 \
  --duplicate-probe \
  --output-dir "$OUT"

The script must not accept:

--audio-path
--text
--prompt
--default-sink
--browser

Those values must come from the accepted render event and the explicit sink preflight.

12. Exact Round 2 stop condition

Round 2 passes only when:

playback.requested exists
playback.started exists
playback.ended exists

and all three:

share the canonical session
share listener-process-1
share the original correlation ID
form render -> requested -> started -> ended causation
are live=true
are mocked=false
carry the exact artifact ID and audio hash
carry the exact Tau-plan hash
carry the exact Jabra node.name

Additionally:

requested sequence < started sequence < ended sequence
requested was appended before Popen
started has two graph snapshots showing streaming and active Jabra routing
ended has exit_code=0 and plausible timing
the stream is absent/not-running after exit
the render claim is acknowledged
the duplicate probe starts no second process
no browser audio was used
no orb event was emitted
the human explicitly confirms hearing the exact sentence

The journal’s total event count need not equal exactly 49 because other producers may append events. The gate should count one matching requested/started/ended chain for the deterministic playback authority ID.

What Round 2 proves

When both machine and human receipts pass, Round 2 proves:

the exact journal-accepted Chatterbox artifact was rehashed
the exact artifact was submitted to pw-play
pw-play targeted the explicit Jabra node.name
the PipeWire stream reached streaming state
an active graph route reached that Jabra sink
the process completed successfully with plausible timing
all lifecycle events retained one session/turn lineage
the same idempotency key did not start a second playback
a human reported hearing the expected sentence
What Round 2 does not prove

It does not prove:

orb state or audio-envelope synchronization
browser playback
browser microphone input
self-audio suppression
continuous full-duplex listening
replay
interruption or stale-buffer flushing
acoustic quality under noise
hardware output at native 24 kHz mono
the 200+/300 integrated suite

PipeWire may resample or remix the 24 kHz mono source before hardware output; this rung proves the exact accepted source artifact and its selected output route, not the physical DAC’s negotiated format.

The Jabra microphone at object ID 62 is not part of this proof and should not be used as an acoustic loopback witness. Doing so would broaden the rung into listening, echo rejection, and self-audio classification.
