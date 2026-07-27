# Embry Live ASR Capture MVP Competition Scorecard

Immutable Goal: NOT_MET

## Objective

Unblock the Embry voice path by proving the smallest non-browser, non-mocked
audio ingress route that turns a Chatterbox-generated wake/command WAV into an
accepted RealtimeSTT/Whisper transcript.

## Candidates

| Candidate | Tab | Status | Useful Features | Local Decision |
| --- | --- | --- | --- | --- |
| WebGPT | `837362257` | responded | virtual monitor fallback, dual physical/virtual proof, receipt gates | accepted features |
| WebGrok | `837362320` | responded | clearest PipeWire topology, explicit monitor port names, Jabra mic as negative control, virtual source plus Jabra audible mirror | winner |
| Gemini | `837362335` | responded | same virtual sink/source topology and Jabra audible mirror | accepted features |
| Kimi | `837362252` | unrelated response | none for this task | rejected |
| Claude | `837362247` | Surf text extraction empty | not locally inspectable | unchecked |

## Accepted Features

- Do not use Jabra speaker to Jabra mic for agent self-triggering.
- Treat the physical Jabra route as a negative control because Jabra AEC/DSP
  suppresses speaker playback before ASR can use it.
- Create a PipeWire virtual sink/source pair for deterministic STT ingress.
- Play Chatterbox audio into the virtual sink and record from the paired virtual
  source.
- Mirror the virtual sink to the Jabra sink only for human-audible playback.
- Preserve physical route failure and virtual route pass in one receipt.
- Use the existing RealtimeSTT listener bridge for local proof.

## Local Proof

Script:

```text
scripts/embry_live_asr_capture_mvp.py
```

Combined physical-negative-control plus virtual-pass receipt:

```text
/tmp/embry-live-asr-capture-mvp-both-20260726T235147Z/summary.json
```

Result:

- `mocked: false`
- `live: true`
- `pass: true`
- `physical_acoustic_path_pass: false`
- `virtual_loopback_path_pass: true`
- physical Jabra transcript: empty string
- virtual transcript: `Hambrey, what is the capital of France? Proof code 6179.`
- virtual RealtimeSTT: `ok: true`

Winner feature combination with Jabra audible mirror:

```text
/tmp/embry-live-asr-capture-mvp-virtual-mirror-20260726T235427Z/summary.json
```

Result:

- `mocked: false`
- `live: true`
- `pass: true`
- `virtual_loopback_path_pass: true`
- `route_setup.jabra_mirror_enabled: true`
- `route_setup.pw_link_embry_lines` includes
  `embry_virtual_speaker:monitor_MONO -> embry_monitor_bridge:input_MONO`
- virtual RealtimeSTT: `ok: true`
- virtual transcript: `Hambrey, what is the capital of France? Proof code 6179.`

## Winner

WebGrok tab `837362320`.

Reason: WebGrok gave the most operationally precise PipeWire route model and
port-name guidance. WebGPT and Gemini converged on the same implementation
pattern, and their locally verified features were harvested into the winner
path.

## What This Proves

```text
Chatterbox WAV -> PipeWire virtual source -> captured WAV ->
RealtimeSTT bridge -> live Whisper executor -> accepted command transcript
```

It also proves the Jabra mic physical route remains a failing negative control
under the same source audio.

## What Remains

This is not the full Embry voice goal. The next slice is wiring the proven
virtual source into the actual Embry listener turn path and producing a fresh
full-turn receipt:

```text
virtual wake/input -> RealtimeSTT final transcript -> SPARTA live turn ->
Chatterbox response -> Jabra playback -> orb CDP state/audio proof
```
