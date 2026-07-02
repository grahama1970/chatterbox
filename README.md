# Chatterbox Voice Agent Fork

This repository is our Chatterbox fork for Embry-style voice-agent rendering.
It keeps the upstream Resemble AI Chatterbox models, and adds a local FastAPI
Chatterbox Turbo agent server with ASR-gated audio acceptance, sentence-aware
Turbo chunking, interruptible PCM streaming, turn controls, conversation sanity
receipts, and memory-gated blessed-QRA instant playback.

Current primary runtime:

```text
listener/coordinator text -> memory/QRA gate when available ->
Chatterbox Turbo render plan -> ASR-gated or blessed cached audio ->
PCM stream / WAV receipts
```

Chatterbox remains the renderer. Memory, QRA trust, search/tool use, reasoning,
and emotional steering decisions belong to the coordinator and memory pipeline.

## Fork Additions

| Area | Current implementation |
| --- | --- |
| Agent server | `src/chatterbox/agent/server.py` exposes `/health`, `/presets`, `/render-plan`, `/synthesize`, `/synthesize-batch`, `/synthesize-batch-stream`, `/tau/voice-render`, `/turn/{turn_id}/cancel`, `/playback/{turn_id}/duck`, and `/playback/{turn_id}/stop`. |
| Docker launcher | `scripts/start_agent_server_docker.sh` starts the server on `127.0.0.1:8018`, mounting this repo read-only and `/tmp/chatterbox-fork-agent-out` as `/out`. |
| ASR acceptance | `/synthesize-batch` can render multiple candidates, transcribe through the configured OpenAI-compatible Whisper endpoint, accept the first candidate passing WER/duration/repetition gates, and cache accepted WAV audio. |
| Turbo chunking | `src/chatterbox/agent/chunking.py` hard-clamps chunks to 300 characters, preserves word boundaries, records hashes, delivery stage, pause metadata, and interruptibility. |
| Streaming | `/synthesize-batch-stream` streams signed 16-bit little-endian PCM chunks and honors `turn_id` cancellation/stop state before synthesis and before PCM block emission. |
| Turn controls | Cancel, duck, and stop endpoints record live turn-control state; cancel/stop can terminate matching stream playback. |
| Blessed QRA cache | Approved QRA creation events can invoke `scripts/qra_creation_audio_hook.py`, which uses `scripts/bless_qra_audio_variants.py` to pre-render five Embry audio variants; runtime playback requires a near-exact memory/QRA gate by default. |
| Conversation ladder | `scripts/smoke_conversation_ladder.py` and `docs/conversation_sanity_ladder_v0.md` define rungs 1-7 for file-backed listener input, state, memory, interruption, Brave Search latency, emotional steering, and listener-boundary receipts. |
| Listener contract | Rung 7 has a live boundary runner: audio frames in, ASR/heard-text ledger out, coordinator turn events out, and a `tau.voice_render_request.v1` envelope. |

## Quick Start: Agent Server

The Docker launcher is dry-run by default:

```bash
./scripts/start_agent_server_docker.sh
./scripts/start_agent_server_docker.sh --execute
```

The launcher expects an existing Whisper container named `whisper`, creates or
uses the Docker network `chatterbox-voice-net`, attaches Whisper with the
`whisper` DNS alias, and starts Chatterbox on `http://127.0.0.1:8018`.

Run a basic server smoke:

```bash
python scripts/smoke_agent_server.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/smoke-agent-server.json
```

## API Surface

Primary request models live in `src/chatterbox/agent/server.py`:

- `RenderPlanRequest`: `answer_text`, `max_chars`, `pause_after_ms`,
  `completion_cue`.
- `SynthesisRequest`: single text render with optional `ref_audio`,
  `delivery_stage`, and supported Turbo generation parameters.
- `SynthesisBatchRequest`: render/stream batch request with ASR gates,
  `turn_id`, blessed-QRA cache controls, variant selection, and memory gate
  fields.
- `TauVoiceRenderRequest`: Embry/Tau coordinator envelope accepted by
  `/tau/voice-render`; preserves listener evidence, memory route metadata,
  text hashes, turn controls, and blessed-QRA gate fields before mapping into
  the batch renderer.
- `TurnControlRequest`: cancel/duck/stop reason and old/new turn ids.

Important environment variables:

| Variable | Purpose |
| --- | --- |
| `CHATTERBOX_OUT_DIR` | Output/cache directory inside the server container, default `/out`. |
| `CHATTERBOX_REF_AUDIO` | Default voice reference audio path. |
| `CHATTERBOX_REF_AUDIO_ROOTS` | Colon-separated allowed roots for reference audio paths. |
| `CHATTERBOX_DEVICE` | Model device, default `cuda`. |
| `CHATTERBOX_ASR_OPENAI_BASE_URL` | Server-side Whisper/OpenAI-compatible ASR base URL. |
| `CHATTERBOX_ASR_API_KEY_ENV` | Environment variable name for the ASR API key, default `WHISPER_API_KEY`. |
| `CHATTERBOX_BLESSED_QRA_LEDGER` | Optional blessed-QRA audio ledger path, default `/out/_blessed_qra_ledger.json`. |

## ASR-Gated Audio Cache

Run the ASR-gated batch smoke:

```bash
python scripts/smoke_asr_gated_batch.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/smoke-asr-gated-batch-script.json
```

The smoke writes a receipt with `mocked=false`, `live=true`, chunk-level ASR
candidate gates, accepted candidate indexes, and the finished response audio
path.

Accepted ASR-gated chunks are cached under `/out/_accepted_audio_cache` inside
the container. Repeating the same text, delivery stage, reference audio, ASR
gates, and candidate policy can reuse accepted audio instead of rendering again:

```bash
python scripts/smoke_asr_gated_batch.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/smoke-asr-cache-fill.json

python scripts/smoke_asr_gated_batch.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/smoke-asr-cache-hit.json \
  --expect-cache-hit
```

## Streaming And Turn Controls

Run the raw PCM chunk-stream smoke:

```bash
python scripts/smoke_stream_endpoint.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/smoke-stream-endpoint-script.json
```

This stream smoke proves the chunked `audio/L16` transport and playable PCM
conversion only. It intentionally does not claim ASR text fidelity.

Run the focused stream-cancel smoke:

```bash
python scripts/smoke_stream_turn_cancel.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/stream-cancel-smoke.json
```

`/synthesize-batch-stream` accepts an optional `turn_id`. When the matching
turn-control state is cancelled or stopped, the stream generator stops before
synthesis and before PCM block emission. The smoke proves a baseline stream
emits bytes and a pre-cancelled old turn emits zero bytes.

## Blessed QRA Instant Playback

Known, reviewed QRA answers can be pre-rendered into Embry audio variants and
played back without waiting for new Chatterbox generation. This path is
fail-closed: local text similarity is not enough by default. The caller must
provide a memory/QRA gate from the coordinator:

- `blessed_qra_memory_key` must match the blessed QRA entry.
- `blessed_qra_memory_similarity` must meet `blessed_qra_min_similarity`
  (default `0.99`).
- `blessed_qra_memory_review_status` must be `approved`, `blessed`, or
  `verified`.
- Set `use_blessed_qra_cache=false` to disable this fast path for a request.

At QRA creation/review time, pass an approved QRA event to the hook:

```bash
python scripts/qra_creation_audio_hook.py \
  --event /path/to/qra-creation-event.json \
  --receipt /tmp/chatterbox-fork-agent-out/qra-creation-audio-hook.json \
  --base-url http://127.0.0.1:8018 \
  --ledger /tmp/chatterbox-fork-agent-out/_blessed_qra_ledger.json \
  --host-out-dir /tmp/chatterbox-fork-agent-out
```

The hook fails closed unless the event has `review_status` of `approved`,
`blessed`, or `verified`, has question/answer/memory key fields, and requests
five variants. Pass `--disable-auto-generation` to skip creation-time audio for
that invocation. The lower-level renderer utility can still create or refresh
the five Embry audio variants directly:

```bash
python scripts/bless_qra_audio_variants.py \
  --base-url http://127.0.0.1:8018 \
  --ledger /tmp/chatterbox-fork-agent-out/_blessed_qra_ledger.json \
  --host-out-dir /tmp/chatterbox-fork-agent-out \
  --qra-id qra-smoke-si \
  --memory-key qra-smoke-si \
  --question "Which control family should I use when the answer says SI?" \
  --answer "Use system and communications protection."
```

Use a cached variant from `/synthesize-batch` by passing `question_text`,
`blessed_qra_variant`, and the memory gate fields. Set
`blessed_qra_preserve_pauses=true` to keep a variant's recorded pause profile;
leave it false for fastest playback.

## Conversation Sanity Ladder

The current ladder is documented in `docs/conversation_sanity_ladder_v0.md` and
audited in `docs/conversation_sanity_ladder_audit.md`.

Implemented evidence rungs:

| Rung | Scope |
| --- | --- |
| 1 | File-backed listener input through ASR/TTS loop. |
| 2 | Two-turn state and fail-closed missing context. |
| 3 | Memory-grounded response with preserved recall evidence. |
| 4 | Interruption harness, stale old-turn skip, live cancel/duck/stop controls. |
| 5 | Brave Search/tool-latency wait behavior with source URLs. |
| 6 | Dynamic emotion cue extraction, memory comparison, and utterance policy receipts. |

Rung 7 is implemented as a listener-boundary runner. It accepts a WAV transport,
records frame-level listener events, runs the configured ASR backend, writes
`heard-text-ledger.jsonl`, `listener-turn-events.jsonl`, `asr-transcript.json`,
and creates `tau-voice-render-request.json`. It does not call memory, search, or
Chatterbox directly. A local run on this checkout failed closed because
`faster_whisper` was unavailable.

## Full Live Sanity Bundle

Run the combined live sanity bundle:

```bash
python scripts/smoke_full_live_sanity.py \
  --base-url http://127.0.0.1:8018 \
  --out-dir /tmp/chatterbox-fork-agent-out/full-live-sanity-$(date -u +%Y%m%dT%H%M%SZ) \
  --reset-cache
```

The bundle chains ASR-gated cache fill, ASR-gated cache hit, raw chunk-stream
transport, stream-cancel proof, interruption handling, and live cancel/duck/stop
turn-control endpoints into one index receipt. It records `mocked=false`,
`live=true`, child receipt paths, cache reset method, stale chunk skip counts,
stream first-byte timing, final turn-control state, and explicit
`does_not_prove` boundaries. If the accepted audio cache is container-owned, the
runner falls back to deleting `/out/_accepted_audio_cache` from inside
`chatterbox-fork-agent-server`. Add `--include-listener-rung7` when a local or
OpenAI-compatible ASR backend is available and you want the listener-boundary
receipt included in the same bundle. Add `--include-tau-voice-render` to include
the Embry/Tau render ingress smoke. Add `--include-listener-memory-tau-qra` to
exercise the listener -> memory/QRA -> Tau render -> blessed audio cache chain.

Focused Tau ingress smoke:

```bash
python scripts/smoke_tau_voice_render.py \
  --base-url http://127.0.0.1:8018 \
  --out /tmp/chatterbox-fork-agent-out/tau-voice-render-smoke.json \
  --expect-cache-hit
```

Focused combined chain smoke:

```bash
WHISPER_API_KEY=<token> python scripts/smoke_listener_memory_tau_qra.py \
  --out-dir /tmp/chatterbox-fork-agent-out/listener-memory-tau-qra-smoke
```

## Current Proof Artifacts

The latest recorded proof artifacts are local files under
`/tmp/chatterbox-fork-agent-out/`:

| Artifact | What it proves |
| --- | --- |
| `conversation-ladder/rung1-live-20260702T111209Z/rung1.json` through `rung6-live-20260702T113313Z/rung6.json` | Rungs 1-6 with `mocked=false`, `live=true`, and empty `failed_gates`. |
| `stream-cancel-20260702T1150/stream-cancel.json` | Pre-cancelled stream emits zero old-turn bytes after cancel. |
| `blessed-qra-cache-hit-20260702T1214.json` | Near-exact approved memory gate can select a blessed Embry QRA variant and return cached audio in `157.103 ms`. |
| `tau-voice-render-20260702T134405Z.json` | Restarted server accepted `tau.voice_render_request.v1`, mapped it to batch rendering, selected the blessed QRA `gentle` variant, and wrote host WAV metrics with `mocked=false`, `live=true`, and empty `failed_gates`. |
| `conversation-ladder/rung7-live-openai/rung7.json` | Rung 7 listener boundary with OpenAI-compatible Whisper: 137 audio frame events, final transcript WER `0.0`, heard-text ledger, coordinator events, and `tau.voice_render_request.v1`; `mocked=false`, `live=true`, empty `failed_gates`. |
| `listener-memory-tau-qra-20260702T135037Z/listener-memory-tau-qra.json` | Full listener -> memory/QRA -> Tau render -> blessed cache chain: live heard text, live `sparta_qra` recall key `qra__run-recovery-verify__2085979782`, five generated Embry variants, Tau cache hit, memory gate passed, and host WAV metrics. |
| `listener-memory-tau-qra-20260702T140108Z-creation-hook/listener-memory-tau-qra.json` | Same combined chain routed through `qra_creation_audio_hook.py`: approved QRA creation event, hook `live=true`, five generated variants over two chunks, Tau cache hit, memory gate passed, selected variant `gentle`, and host WAV `1198158` bytes / `24.96` seconds. |
| `full-live-sanity-20260702T140317Z-creation-hook/full-live-sanity.json` | Augmented full bundle with ASR cache fill/hit, stream, stream cancel, interruption, turn controls, Tau ingress, and listener-memory-QRA creation-hook chain all `mocked=false`, `live=true`, and empty `failed_gates`. |

These receipts do not prove live microphone capture, WebRTC/browser transport,
production memory-agent admission review, subjective voice quality, noisy-room
robustness, or mid-buffer audio-device flush after cancellation.

## Upstream Chatterbox

![Chatterbox Multilingual Image](./Chatterbox-Multilingual.png)

[![Alt Text](https://img.shields.io/badge/listen-demo_samples-blue)](https://resemble-ai.github.io/chatterbox_demopage/)
[![Alt Text](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS)
[![Alt Text](https://static-public.podonos.com/badges/insight-on-pdns-sm-dark.svg)](https://podonos.com/resembleai/chatterbox)
[![Discord](https://img.shields.io/discord/1377773249798344776?label=join%20discord&logo=discord&style=flat)](https://discord.gg/rJq9cRJBJ6)

*Made with love by* <a href="https://resemble.ai" target="_blank"><img width="100" alt="resemble-logo-horizontal" src="https://github.com/user-attachments/assets/35cf756b-3506-4943-9c72-c05ddfa4e525" /></a>

**Chatterbox** is a family of state-of-the-art, open-source text-to-speech models by Resemble AI.

## Latest Release: Chatterbox Multilingual V3

**Chatterbox Multilingual V3** is the latest general-purpose multilingual TTS model in the Chatterbox family. It keeps the same 0.5B model size while improving speaker similarity, reducing hallucinations, and producing more natural, conversational speech across languages.

V3 is designed for broad language coverage like V2, but with stronger stability and more expressive generation. It is the recommended multilingual model for users who want one voice cloning model that works across many languages.

Alongside V3, we are releasing the **Single Language Pack**: dedicated finetunes for priority languages where tighter quality control, stronger language-specific behavior, and more specialized speech generation are valuable.

- **Broad Multilingual Coverage:** Designed as the main general-purpose multilingual Chatterbox model, supporting wide language coverage similar to V2.
- **Single Language Pack:** Dedicated single-language models provide stronger specialization and quality control where language- and regional-dialect-specific performance matters most.
- **More Consistent Speaker Similarity:** Improves voice identity and accent preservation across languages, making cross-language voice cloning more stable and reliable.
- **Reduced Hallucination:** V3 is optimized to reduce unwanted continuation, repetition, and off-prompt speech, especially in cases where earlier multilingual models were less stable.

For low-latency English voice agents, **Chatterbox-Turbo** is our most efficient model. Built on a streamlined 350M parameter architecture, **Turbo** delivers high-quality speech with less compute and VRAM than our previous models. We have also distilled the speech-token-to-mel decoder, previously a bottleneck, reducing generation from 10 steps to just **one**, while retaining high-fidelity audio output.

**Paralinguistic tags** are now native to the Turbo model, allowing you to use `[cough]`, `[laugh]`, `[chuckle]`, and more to add distinct realism. While Turbo was built primarily for low-latency voice agents, it excels at narration and creative workflows.

If you like the model but need to scale or tune it for higher accuracy, check out our competitively priced TTS service (<a href="https://resemble.ai">link</a>). It delivers reliable performance with ultra-low latency of sub 200ms—ideal for production use in agents, applications, or interactive media.

<img width="1200" height="600" alt="Podonos Turbo Eval" src="https://storage.googleapis.com/chatterbox-demo-samples/turbo/podonos_turbo.png" />

### ⚡ Model Zoo

Choose the right model for your application.

| Model                                                                                                           | Size | Languages | Key Features                                            | Best For                                     | 🤗                                                                  | Examples |
|:----------------------------------------------------------------------------------------------------------------| :--- | :--- |:--------------------------------------------------------|:---------------------------------------------|:--------------------------------------------------------------------------| :--- |
| **Chatterbox-Turbo**                                                                                            | **350M** | **English** | Paralinguistic Tags (`[laugh]`), Lower Compute and VRAM | Zero-shot voice agents,  Production          | [Demo](https://huggingface.co/spaces/ResembleAI/chatterbox-turbo-demo)        | [Listen](https://resemble-ai.github.io/chatterbox_turbo_demopage/) |
| **Chatterbox-Multilingual V3** [(Language list)](#supported-languages)                                          | **500M** | **23+** | Improved speaker similarity, reduced hallucinations, more natural multilingual speech | Global applications, localization, cross-language voice cloning | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS) | [Listen](https://resemble-ai.github.io/chatterbox_demopage/) |
| **Single Language Pack** [(Models)](#single-language-pack)                                                      | 500M each | 6 dedicated finetunes | Language- and region-specific quality control           | Priority languages and dialect-sensitive applications | [Models](#single-language-pack) | [Demos](#single-language-pack) |
| Chatterbox [(Tips and Tricks)](#original-chatterbox-tips)                                                       | 500M | English | CFG & Exaggeration tuning                               | General zero-shot TTS with creative controls | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox)              | [Listen](https://resemble-ai.github.io/chatterbox_demopage/) |

## Installation
```shell
pip install chatterbox-tts
```

Alternatively, you can install from source:
```shell
# conda create -yn chatterbox python=3.11
# conda activate chatterbox

git clone https://github.com/resemble-ai/chatterbox.git
cd chatterbox
pip install -e .
```
We developed and tested Chatterbox on Python 3.11 on Debian 11 OS; the versions of the dependencies are pinned in `pyproject.toml` to ensure consistency. You can modify the code or dependencies in this installation mode.

## Usage

##### Chatterbox-Turbo

```python
import torchaudio as ta
import torch
from chatterbox.tts_turbo import ChatterboxTurboTTS

# Load the Turbo model
model = ChatterboxTurboTTS.from_pretrained(device="cuda")

# Generate with Paralinguistic Tags
text = "Hi there, Sarah here from MochaFone calling you back [chuckle], have you got one minute to chat about the billing issue?"

# Generate audio (requires a reference clip for voice cloning)
wav = model.generate(text, audio_prompt_path="your_10s_ref_clip.wav")

ta.save("test-turbo.wav", wav, model.sr)
```

##### Chatterbox and Chatterbox-Multilingual

```python

import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

device = "cuda"  # or "cpu" / "mps"

# English example
model = ChatterboxTTS.from_pretrained(device=device)

text = "Ezreal and Jinx teamed up with Ahri, Yasuo, and Teemo to take down the enemy's Nexus in an epic late-game pentakill."
wav = model.generate(text)
ta.save("test-english.wav", wav, model.sr)

# Multilingual V3 examples
multilingual_model = ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model="v3")
# To use the legacy V2 multilingual checkpoint, omit t3_model or pass t3_model="v2".

french_text = "Bonjour, comment ça va? Ceci est le modèle de synthèse vocale multilingue Chatterbox, il prend en charge 23 langues."
wav_french = multilingual_model.generate(french_text, language_id="fr")
ta.save("test-french.wav", wav_french, multilingual_model.sr)

chinese_text = "你好，今天天气真不错，希望你有一个愉快的周末。"
wav_chinese = multilingual_model.generate(chinese_text, language_id="zh")
ta.save("test-chinese.wav", wav_chinese, multilingual_model.sr)

# If you want to synthesize with a different voice, specify the audio prompt
AUDIO_PROMPT_PATH = "YOUR_FILE.wav"
wav = model.generate(text, audio_prompt_path=AUDIO_PROMPT_PATH)
ta.save("test-2.wav", wav, model.sr)
```
See `example_tts.py` and `example_vc.py` for more examples.

## Supported Languages
The general-purpose Chatterbox Multilingual model supports the following languages:

Arabic (ar) • Danish (da) • German (de) • Greek (el) • English (en) • Spanish (es) • Finnish (fi) • French (fr) • Hebrew (he) • Hindi (hi) • Italian (it) • Japanese (ja) • Korean (ko) • Malay (ms) • Dutch (nl) • Norwegian (no) • Polish (pl) • Portuguese (pt) • Russian (ru) • Swedish (sv) • Swahili (sw) • Turkish (tr) • Chinese (zh)

## Single Language Pack

The Single Language Pack provides dedicated finetunes for priority languages and regional variants. Use these when you want stronger language-specific behavior, tighter quality control, or dialect-aware generation beyond the general multilingual model.

| Language | Model Card | Demo Space |
| --- | --- | --- |
| Chinese | [ResembleAI/Chatterbox-Multilingual-zh-cmn](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-zh-cmn) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-zh-cmn) |
| Latam Spanish | [ResembleAI/Chatterbox-Multilingual-es-mx-latam](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-mx-latam) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-es-mx-latam) |
| Brazilian Portuguese | [ResembleAI/Chatterbox-Multilingual-pt-br](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-pt-br) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-pt-br) |
| Spain Spanish | [ResembleAI/Chatterbox-Multilingual-es-es](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-es) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-es-es) |
| Portugal Portuguese | [ResembleAI/Chatterbox-Multilingual-pt-pt](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-pt-pt) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-pt-pt) |
| Hindi | [ResembleAI/Chatterbox-Multilingual-hi](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-hi) | [Demo](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-hi) |

## Original Chatterbox Tips
- **General Use (TTS and Voice Agents):**
  - Ensure that the reference clip matches the specified language tag. Otherwise, language transfer outputs may inherit the accent of the reference clip’s language. To mitigate this, set `cfg_weight` to `0`.
  - The default settings (`exaggeration=0.5`, `cfg_weight=0.5`) work well for most prompts across all languages.
  - If the reference speaker has a fast speaking style, lowering `cfg_weight` to around `0.3` can improve pacing.

- **Expressive or Dramatic Speech:**
  - Try lower `cfg_weight` values (e.g. `~0.3`) and increase `exaggeration` to around `0.7` or higher.
  - Higher `exaggeration` tends to speed up speech; reducing `cfg_weight` helps compensate with slower, more deliberate pacing.


## Built-in PerTh Watermarking for Responsible AI

Every audio file generated by Chatterbox includes [Resemble AI's Perth (Perceptual Threshold) Watermarker](https://github.com/resemble-ai/perth) - imperceptible neural watermarks that survive MP3 compression, audio editing, and common manipulations while maintaining nearly 100% detection accuracy.


## Watermark extraction

You can look for the watermark using the following script.

```python
import perth
import librosa

AUDIO_PATH = "YOUR_FILE.wav"

# Load the watermarked audio
watermarked_audio, sr = librosa.load(AUDIO_PATH, sr=None)

# Initialize watermarker (same as used for embedding)
watermarker = perth.PerthImplicitWatermarker()

# Extract watermark
watermark = watermarker.get_watermark(watermarked_audio, sample_rate=sr)
print(f"Extracted watermark: {watermark}")
# Output: 0.0 (no watermark) or 1.0 (watermarked)
```


## Official Discord

👋 Join us on [Discord](https://discord.gg/rJq9cRJBJ6) and let's build something awesome together!

## Evaluation
Chatterbox Turbo was evaluated using Podonos, a platform for reproducible subjective speech evaluation.

We compared Chatterbox Turbo to competitive TTS systems using Podonos' standardized evaluation suite, focusing on overall preference, naturalness, and expressiveness.

Evaluation reports:
- [Chatterbox Turbo vs ElevenLabs Turbo v2.5](https://podonos.com/resembleai/chatterbox-turbo-vs-elevenlabs-turbo)
- [Chatterbox Turbo vs Cartesia Sonic 3](https://podonos.com/resembleai/chatterbox-turbo-vs-cartesia-sonic3)
- [Chatterbox Turbo vs VibeVoice 7B](https://podonos.com/resembleai/chatterbox-turbo-vs-vibevoice7b)

These evaluations were conducted under identical conditions and are publicly accessible via Podonos.

## Acknowledgements
- [Podonos](https://podonos.com) — for supporting reproducible subjective speech evaluation
- [Cosyvoice](https://github.com/FunAudioLLM/CosyVoice)
- [Real-Time-Voice-Cloning](https://github.com/CorentinJ/Real-Time-Voice-Cloning)
- [HiFT-GAN](https://github.com/yl4579/HiFTNet)
- [Llama 3](https://github.com/meta-llama/llama3)
- [S3Tokenizer](https://github.com/xingchensong/S3Tokenizer)

## Citation
If you find this model useful, please consider citing.
```
@misc{chatterboxtts2025,
  author       = {{Resemble AI}},
  title        = {{Chatterbox-TTS}},
  year         = {2025},
  howpublished = {\url{https://github.com/resemble-ai/chatterbox}},
  note         = {GitHub repository}
}
```
## Disclaimer
Don't use this model to do bad things. Prompts are sourced from freely available data on the internet.
