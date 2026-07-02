#!/usr/bin/env bash
set -euo pipefail

execute=false
network="${CHATTERBOX_DOCKER_NETWORK:-chatterbox-voice-net}"
chatterbox_container="${CHATTERBOX_CONTAINER_NAME:-chatterbox-fork-agent-server}"
whisper_container="${WHISPER_CONTAINER_NAME:-whisper}"
image="${CHATTERBOX_DOCKER_IMAGE:-chatterbox-voice-sanity:local}"
host_port="${CHATTERBOX_HOST_PORT:-8018}"
container_port="${CHATTERBOX_CONTAINER_PORT:-8018}"
repo_root="${CHATTERBOX_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
out_dir="${CHATTERBOX_OUT_DIR_HOST:-/tmp/chatterbox-fork-agent-out}"
ref_audio="${CHATTERBOX_REF_AUDIO_HOST:-/home/graham/workspace/experiments/agent-skills/skills/persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav}"
device="${CHATTERBOX_DEVICE:-cuda}"
asr_url="${CHATTERBOX_ASR_OPENAI_BASE_URL:-http://whisper:9000}"
diarization_python="${CHATTERBOX_DIARIZATION_PYTHON:-/opt/chatterbox-diarization-venv/bin/python}"
hf_token="${HF_TOKEN:-}"
if [[ -z "$hf_token" ]] && command -v zsh >/dev/null 2>&1; then
  hf_token="$(zsh -lc 'source ~/.zshrc >/dev/null 2>&1; print -r -- ${HF_TOKEN:-}' || true)"
fi

usage() {
  cat <<EOF
Usage: $0 [--execute]

Dry-run by default. With --execute, this creates/uses a Docker network,
connects the existing Whisper container with alias "whisper", and restarts the
Chatterbox agent server on 127.0.0.1:${host_port}.

Environment overrides:
  CHATTERBOX_DOCKER_NETWORK      default: ${network}
  CHATTERBOX_CONTAINER_NAME      default: ${chatterbox_container}
  WHISPER_CONTAINER_NAME         default: ${whisper_container}
  CHATTERBOX_DOCKER_IMAGE        default: ${image}
  CHATTERBOX_HOST_PORT           default: ${host_port}
  CHATTERBOX_REPO_ROOT           default: ${repo_root}
  CHATTERBOX_OUT_DIR_HOST        default: ${out_dir}
  CHATTERBOX_REF_AUDIO_HOST      default: ${ref_audio}
  CHATTERBOX_ASR_OPENAI_BASE_URL default: ${asr_url}
  CHATTERBOX_DIARIZATION_PYTHON  default: ${diarization_python}
  HF_TOKEN                       optional; used for gated pyannote model access
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      execute=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -d "$repo_root/src/chatterbox" ]]; then
  echo "repo root does not look like chatterbox: $repo_root" >&2
  exit 2
fi
if [[ ! -f "$ref_audio" ]]; then
  echo "reference audio missing: $ref_audio" >&2
  exit 2
fi
if ! docker inspect "$whisper_container" >/dev/null 2>&1; then
  echo "Whisper container not found: $whisper_container" >&2
  exit 2
fi
if ! docker inspect "$image" >/dev/null 2>&1; then
  echo "Chatterbox image not found: $image" >&2
  exit 2
fi

echo "network=$network"
echo "chatterbox_container=$chatterbox_container"
echo "whisper_container=$whisper_container"
echo "image=$image"
echo "host_port=$host_port"
echo "repo_root=$repo_root"
echo "out_dir=$out_dir"
echo "ref_audio=$ref_audio"
echo "asr_url=$asr_url"
echo "diarization_python=$diarization_python"
if [[ -n "$hf_token" ]]; then
  echo "hf_token=set"
else
  echo "hf_token=unset"
fi
echo "execute=$execute"

if [[ "$execute" != true ]]; then
  cat <<EOF
Dry run only. Planned actions:
  docker network inspect/create ${network}
  docker network connect --alias whisper ${network} ${whisper_container} if needed
  docker rm -f ${chatterbox_container} if present
  docker run ${image} with GPU, repo/output/reference mounts, and ASR URL ${asr_url}
Run with --execute to apply.
EOF
  exit 0
fi

mkdir -p "$out_dir"
docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network" >/dev/null
if ! docker inspect "$whisper_container" --format '{{json .NetworkSettings.Networks}}' | grep -q "\"${network}\""; then
  docker network connect --alias whisper "$network" "$whisper_container"
fi

key_file="$(mktemp /tmp/chatterbox-whisper-key.XXXXXX)"
trap 'rm -f "$key_file"' EXIT
docker exec "$whisper_container" sh -lc 'cat /var/lib/whisper/.api_key' > "$key_file"
chmod 600 "$key_file"

docker_env=(
  -e PYTHONPATH=/work/src
  -e CHATTERBOX_OUT_DIR=/out
  -e CHATTERBOX_REF_AUDIO=/data/embry_ref.wav
  -e CHATTERBOX_REF_AUDIO_ROOTS=/data:/voices:/work
  -e CHATTERBOX_DEVICE="$device"
  -e CHATTERBOX_ASR_OPENAI_BASE_URL="$asr_url"
  -e CHATTERBOX_DIARIZATION_PYTHON="$diarization_python"
  -e WHISPER_API_KEY="$(cat "$key_file")"
)
if [[ -n "$hf_token" ]]; then
  docker_env+=(-e HF_TOKEN="$hf_token")
fi

docker rm -f "$chatterbox_container" >/dev/null 2>&1 || true
docker run -d \
  --gpus all \
  --name "$chatterbox_container" \
  --network "$network" \
  --entrypoint python3.11 \
  -p "127.0.0.1:${host_port}:${container_port}" \
  "${docker_env[@]}" \
  -v "${repo_root}:/work:ro" \
  -v "${out_dir}:/out" \
  -v "${ref_audio}:/data/embry_ref.wav:ro" \
  "$image" \
  -m uvicorn chatterbox.agent.server:app --host 0.0.0.0 --port "$container_port"

python3 - <<PY
import json
import time
import urllib.request

url = "http://127.0.0.1:${host_port}/health"
last = None
for _ in range(180):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
        if data.get("ok"):
            print(json.dumps({
                "ok": True,
                "url": url,
                "engine": data.get("engine"),
                "device": data.get("device"),
                "model_load_seconds": data.get("model_load_seconds"),
                "voice_conditioning_cache_size": data.get("voice_conditioning_cache_size"),
            }, sort_keys=True))
            raise SystemExit(0)
        last = data
    except Exception as exc:
        last = f"{type(exc).__name__}: {exc}"
    time.sleep(1)
print(json.dumps({"ok": False, "url": url, "last": last}, sort_keys=True))
raise SystemExit(1)
PY
