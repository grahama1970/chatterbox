#!/usr/bin/env python3
"""Prove browser getUserMedia audio transport into a local listener socket.

This smoke intentionally does not use Chromium's fake media-device flags. It
opens a localhost page, grants microphone permission, captures audio through
browser WebRTC/getUserMedia APIs, streams Float32 PCM chunks over WebSocket,
and writes a receipt from the Python listener side.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import socket
import struct
import tempfile
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Chatterbox WebRTC Transport Smoke</title>
</head>
<body>
<script>
window.__webrtcSmoke = {
  status: "idle",
  chunksSent: 0,
  errors: [],
  metadata: null,
  async start(wsUrl, captureMs) {
    this.status = "starting";
    const devicesBefore = await navigator.mediaDevices.enumerateDevices();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      },
      video: false
    });
    const devicesAfter = await navigator.mediaDevices.enumerateDevices();
    const track = stream.getAudioTracks()[0];
    const settings = track ? track.getSettings() : {};
    const constraints = track ? track.getConstraints() : {};
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const socket = new WebSocket(wsUrl);
    socket.binaryType = "arraybuffer";
    const opened = new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = () => reject(new Error("websocket_error"));
    });
    await opened;
    this.metadata = {
      userAgent: navigator.userAgent,
      secureContext: window.isSecureContext,
      sampleRate: audioContext.sampleRate,
      trackSettings: settings,
      trackConstraints: constraints,
      devicesBefore: devicesBefore.map(d => ({kind: d.kind, label: d.label, deviceIdPresent: Boolean(d.deviceId)})),
      devicesAfter: devicesAfter.map(d => ({kind: d.kind, label: d.label, deviceIdPresent: Boolean(d.deviceId)}))
    };
    socket.send(JSON.stringify({type: "metadata", metadata: this.metadata}));
    processor.onaudioprocess = event => {
      const input = event.inputBuffer.getChannelData(0);
      const copy = new Float32Array(input.length);
      copy.set(input);
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(copy.buffer);
        this.chunksSent += 1;
      }
    };
    source.connect(processor);
    processor.connect(audioContext.destination);
    this.status = "capturing";
    await new Promise(resolve => setTimeout(resolve, captureMs));
    processor.disconnect();
    source.disconnect();
    track.stop();
    await audioContext.close();
    socket.send(JSON.stringify({type: "done", chunksSent: this.chunksSent}));
    socket.close();
    this.status = "done";
    return {status: this.status, chunksSent: this.chunksSent, metadata: this.metadata};
  }
};
</script>
</body>
</html>
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_wav_float32(path: Path, samples: list[float], sample_rate: int) -> None:
    pcm = bytearray()
    for sample in samples:
        clipped = max(-1.0, min(1.0, sample))
        pcm.extend(struct.pack("<h", int(round(clipped * 32767.0))))
    data_size = len(pcm)
    riff_size = 36 + data_size
    header = (
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )
    path.write_bytes(header + pcm)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HandlerState:
    def __init__(self) -> None:
        self.metadata: dict[str, Any] | None = None
        self.done: dict[str, Any] | None = None
        self.chunks: list[list[float]] = []
        self.binary_bytes = 0


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright
    import websockets

    started = time.perf_counter()
    failed_gates: list[str] = []
    state = HandlerState()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    wav_path = out.with_suffix(".wav")

    async def ws_handler(websocket: Any) -> None:
        async for message in websocket:
            if isinstance(message, str):
                payload = json.loads(message)
                if payload.get("type") == "metadata":
                    state.metadata = payload.get("metadata") or {}
                elif payload.get("type") == "done":
                    state.done = payload
            else:
                state.binary_bytes += len(message)
                count = len(message) // 4
                if count:
                    state.chunks.append(list(struct.unpack("<" + "f" * count, message[: count * 4])))

    http_port = find_free_port()
    ws_port = find_free_port()
    tmp_dir = Path(tempfile.mkdtemp(prefix="chatterbox-webrtc-page-"))
    (tmp_dir / "index.html").write_text(HTML, encoding="utf-8")
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_dir))
    httpd = ThreadingHTTPServer(("127.0.0.1", http_port), handler)
    http_thread = Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    browser_result: dict[str, Any] = {}
    launch_args = ["--autoplay-policy=no-user-gesture-required"]
    ws_server = await websockets.serve(ws_handler, "127.0.0.1", ws_port)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=args.chromium,
                headless=args.headless,
                args=launch_args,
            )
            context = await browser.new_context()
            origin = f"http://127.0.0.1:{http_port}"
            await context.grant_permissions(["microphone"], origin=origin)
            page = await context.new_page()
            await page.goto(origin + "/index.html", wait_until="load")
            try:
                browser_result = await page.evaluate(
                    "(args) => window.__webrtcSmoke.start(args.wsUrl, args.captureMs)",
                    {"wsUrl": f"ws://127.0.0.1:{ws_port}", "captureMs": int(args.capture_seconds * 1000)},
                )
            finally:
                await context.close()
                await browser.close()
    except Exception as exc:  # noqa: BLE001
        failed_gates.append("browser_get_user_media_transport")
        browser_result = {"error_type": type(exc).__name__, "error": str(exc)}
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        httpd.shutdown()
        httpd.server_close()

    samples = [sample for chunk in state.chunks for sample in chunk]
    sample_rate = int((state.metadata or {}).get("sampleRate") or 0)
    if samples and sample_rate:
        write_wav_float32(wav_path, samples, sample_rate)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) if samples else 0.0
    max_abs = max((abs(sample) for sample in samples), default=0.0)
    nonzero_ratio = sum(1 for sample in samples if abs(sample) > 1e-5) / len(samples) if samples else 0.0
    duration = len(samples) / sample_rate if sample_rate else 0.0

    fake_media_flags = [flag for flag in launch_args if "fake" in flag.lower()]
    if fake_media_flags:
        failed_gates.append("no_fake_media_flags")
    if state.metadata is None:
        failed_gates.append("browser_metadata_received")
    if len(state.chunks) < args.min_chunks:
        failed_gates.append("min_chunks_received")
    if duration < args.min_duration_seconds:
        failed_gates.append("min_audio_duration")
    if rms < args.min_rms:
        failed_gates.append("min_rms")
    if nonzero_ratio < args.min_nonzero_ratio:
        failed_gates.append("min_nonzero_ratio")

    receipt: dict[str, Any] = {
        "schema": "chatterbox.browser_webrtc_transport.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": not failed_gates,
        "started_at_utc": utc_now(),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "inputs": {
            "chromium": args.chromium,
            "headless": args.headless,
            "capture_seconds": args.capture_seconds,
            "min_chunks": args.min_chunks,
            "min_duration_seconds": args.min_duration_seconds,
            "min_rms": args.min_rms,
            "min_nonzero_ratio": args.min_nonzero_ratio,
            "launch_args": launch_args,
        },
        "browser": browser_result,
        "transport": {
            "http_origin": f"http://127.0.0.1:{http_port}",
            "websocket_url": f"ws://127.0.0.1:{ws_port}",
            "metadata": state.metadata,
            "done": state.done,
            "chunks_received": len(state.chunks),
            "binary_bytes_received": state.binary_bytes,
            "samples_received": len(samples),
            "sample_rate": sample_rate,
            "duration_seconds": round(duration, 3),
            "rms": round(rms, 8),
            "max_abs": round(max_abs, 8),
            "nonzero_ratio": round(nonzero_ratio, 6),
        },
        "artifacts": {
            "receipt": str(out),
            "wav": str(wav_path) if wav_path.exists() else None,
            "wav_sha256": sha256_file(wav_path) if wav_path.exists() else None,
            "wav_bytes": wav_path.stat().st_size if wav_path.exists() else 0,
        },
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "browser_getusermedia_captured_real_microphone_audio",
                "browser_sent_pcm_audio_frames_over_websocket_transport",
                "python_listener_received_auditable_pcm_frames_without_fake_media_flags",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "remote_peer_to_peer_webrtc_across_networks",
                "production_browser_ui",
                "asr_transcription_accuracy",
                "speaker_identity_or_diarization",
                "all_browser_vendor_compatibility",
            ],
        },
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chromium", default="/snap/bin/chromium")
    parser.add_argument("--capture-seconds", default=5.0, type=float)
    parser.add_argument("--min-chunks", default=4, type=int)
    parser.add_argument("--min-duration-seconds", default=1.0, type=float)
    parser.add_argument("--min-rms", default=0.0001, type=float)
    parser.add_argument("--min-nonzero-ratio", default=0.05, type=float)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    args.headless = not args.headed
    receipt = asyncio.run(run_smoke(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "failed_gates": receipt["failed_gates"],
                "out": str(args.out),
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
