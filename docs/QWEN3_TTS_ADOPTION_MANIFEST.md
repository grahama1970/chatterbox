# Qwen3-TTS Adoption Manifest (issue #13)

## Source and pinning

| Item | Value |
| --- | --- |
| Upstream project | https://github.com/QwenLM/Qwen3-TTS |
| Runtime package | `qwen-tts==0.1.1` (PyPI), pinned in `sidecar/requirements-qwen3-tts.txt` |
| Model | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| Model revision (HF sha, reviewed 2026-07-31) | `fd4b254389122332181a7c3db7f27e918eec64e3` |
| Upstream license | Apache-2.0 (QwenLM/Qwen3-TTS `LICENSE`; HF model tag `license:apache-2.0`) |
| Chatterbox license | MIT |

## Copied vs independently implemented

No source code was copied from `QwenLM/Qwen3-TTS` or from
`huggingface/speech-to-speech`. The integration is an independently implemented
adapter pair:

- `sidecar/qwen3_tts_sidecar.py` — FastAPI service written for this repo; calls
  the published `qwen_tts.Qwen3TTSModel` API (`from_pretrained`,
  `generate_voice_clone`) as a library consumer.
- `src/chatterbox/agent/qwen_backend.py` — HTTP client for the
  `chatterbox.qwen_sidecar.v1` contract; imports no Qwen dependencies.

Because no Apache-2.0 source is copied or adapted, no NOTICE propagation is
required; the pinned `qwen-tts` wheel retains its own license metadata inside
the isolated sidecar environment.

## Why a sidecar (integration order decision)

`qwen-tts==0.1.1` pins `transformers==4.57.3`; the Chatterbox runtime container
runs `transformers 5.2.0` (verified in the live container 2026-07-31).
Installing Qwen dependencies into the Chatterbox environment would downgrade
transformers under the production Turbo engine, so the ticket's integration
order #2 (isolated local sidecar with a versioned contract) was selected.
The `huggingface/speech-to-speech` gateway was NOT adopted as a dependency.

## Dependency isolation

- Sidecar env: `sidecar/.venv-qwen` (Python 3.12, `torch==2.6.0+cu124`,
  `transformers==4.57.3`, `qwen-tts==0.1.1`).
- Default Chatterbox installation and container: zero Qwen packages; the
  `qwen3_tts` backend registration imports only stdlib + existing modules
  (proven by `tests/test_qwen_backend.py::test_default_install_never_imports_qwen_dependencies`).

## Preregistered VRAM budget (RTX A5000, 24 GB)

| Component | Budget |
| --- | --- |
| Chatterbox Turbo (resident) | ≤ 6 GB |
| Chatterbox base affect (lazy) | ≤ 4 GB |
| Qwen3-TTS 1.7B bf16 sidecar (lazy) | ≤ 7 GB |
| Headroom (ASR/diarization/system) | remainder |

If measured concurrent residency exceeds 22 GB, the inactive backend must be
deterministically unloaded (`POST /unload` on the sidecar; base-model unloader
in the registry). Measured values are recorded in
`docs/QWEN3_TTS_A5000_PROOF_20260731.json`.

## Authority boundaries

- `qwen3_tts` is explicit-only: auto-selection can only ever produce
  `chatterbox_turbo` or `chatterbox_base_affect`.
- No renderer fallback in either direction (proven by tests and live receipt).
- Promotion/perceptual claims remain gated by issue #7; none are made here.
