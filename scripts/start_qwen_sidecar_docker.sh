#!/usr/bin/env bash
# Start the isolated Qwen3-TTS sidecar (issue #13) in a container that SHARES
# the Chatterbox agent container's network namespace, so the agent reaches it
# at http://127.0.0.1:8019 without any container->host firewall traversal.
#
# The sidecar venv (sidecar/.venv-qwen) and the uv-managed interpreter are
# bind-mounted at their host paths; Qwen weights persist in the host HF cache.
# Start order matters: the Chatterbox container must be running first, and this
# script must be re-run after every Chatterbox container restart.
set -euo pipefail

chatterbox_container="${CHATTERBOX_CONTAINER_NAME:-chatterbox-fork-agent-server}"
sidecar_container="${QWEN_SIDECAR_CONTAINER_NAME:-qwen3-tts-sidecar}"
image="${CHATTERBOX_DOCKER_IMAGE:-chatterbox-voice-sanity:local}"
repo_root="${CHATTERBOX_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
venv_python="${repo_root}/sidecar/.venv-qwen/bin/python"
uv_python_dir="${UV_PYTHON_DIR:-$HOME/.local/share/uv/python}"

if ! docker inspect "$chatterbox_container" >/dev/null 2>&1; then
  echo "chatterbox container not running: $chatterbox_container" >&2
  exit 2
fi
if [[ ! -x "$venv_python" ]]; then
  echo "sidecar venv missing: $venv_python (see sidecar/requirements-qwen3-tts.txt)" >&2
  exit 2
fi

docker rm -f "$sidecar_container" >/dev/null 2>&1 || true
docker run -d \
  --gpus all \
  --name "$sidecar_container" \
  --network "container:${chatterbox_container}" \
  -v "${repo_root}:${repo_root}:ro" \
  -v "${uv_python_dir}:${uv_python_dir}:ro" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e QWEN_TTS_HOST=127.0.0.1 \
  -e QWEN_TTS_PORT="${QWEN_TTS_PORT:-8019}" \
  -e QWEN_TTS_ATTN="${QWEN_TTS_ATTN:-sdpa}" \
  -e QWEN_TTS_MODEL="${QWEN_TTS_MODEL:-Qwen/Qwen3-TTS-12Hz-1.7B-Base}" \
  --entrypoint "$venv_python" \
  "$image" \
  "${repo_root}/sidecar/qwen3_tts_sidecar.py"

for _ in $(seq 1 60); do
  if docker exec "$chatterbox_container" /usr/bin/python3.11 -c \
    "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8019/health', timeout=2)" >/dev/null 2>&1; then
    echo '{"ok": true, "sidecar": "reachable from chatterbox container at 127.0.0.1:8019"}'
    exit 0
  fi
  sleep 2
done
echo '{"ok": false, "error": "sidecar_not_reachable"}' >&2
exit 1
