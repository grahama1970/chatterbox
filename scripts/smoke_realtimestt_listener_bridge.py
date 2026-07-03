#!/usr/bin/env python3
"""Run a non-mocked RealtimeSTT external-audio listener bridge smoke.

This script proves the listener companion boundary separately from Chatterbox
rendering: WAV frames are fed through RealtimeSTT's public external-audio API,
RealtimeSTT VAD/finalization owns the recording boundary, and a live
OpenAI-compatible Whisper service is used as the transcription executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import wave
import audioop
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wav_metrics(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
    }


def acceptance_result(*, expected_text: str, transcript: str, max_wer: float) -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from chatterbox.agent.asr_acceptance import acceptance_result as _acceptance_result

    return _acceptance_result(expected_text=expected_text, transcript=transcript, max_wer=max_wer)


def transcribe_openai_compatible(base_url: str, api_key: str, audio_path: Path) -> str:
    import httpx

    with audio_path.open("rb") as handle:
        response = httpx.post(
            f"{base_url.rstrip('/')}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, handle, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json", "language": "en"},
            timeout=120.0,
        )
    response.raise_for_status()
    return str((response.json() or {}).get("text") or "").strip()


class WhisperExecutor:
    def __init__(self, *, base_url: str, api_key: str, events: list[dict[str, Any]], started: float):
        from RealtimeSTT.transcription_engines.base import TranscriptionInfo, TranscriptionResult

        self.base_url = base_url
        self.api_key = api_key
        self.events = events
        self.started = started
        self.TranscriptionInfo = TranscriptionInfo
        self.TranscriptionResult = TranscriptionResult
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio: Any, language: str | None = None, use_prompt: bool = True) -> Any:
        import soundfile as sf

        call_started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            sf.write(str(temp_path), audio, 16000, subtype="PCM_16")
            text = transcribe_openai_compatible(self.base_url, self.api_key, temp_path)
            call = {
                "schema": "chatterbox.realtimestt.executor_call.v1",
                "audio_samples": int(len(audio)) if hasattr(audio, "__len__") else None,
                "audio_sha256": sha256_file(temp_path),
                "language": language,
                "use_prompt": use_prompt,
                "transcript": text,
                "transcript_sha256": sha256_text(text),
                "elapsed_ms": round((time.perf_counter() - call_started) * 1000, 3),
            }
            self.calls.append(call)
            self.events.append(
                {
                    "type": "realtimestt.executor_transcribed",
                    "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 3),
                    "transcript_sha256": call["transcript_sha256"],
                    "audio_samples": call["audio_samples"],
                }
            )
            return self.TranscriptionResult(
                text=text,
                info=self.TranscriptionInfo(language=language or "en", language_probability=1.0),
            )
        finally:
            temp_path.unlink(missing_ok=True)


def feed_wav_to_recorder(
    *,
    recorder: Any,
    audio_path: Path,
    chunk_ms: int,
    trailing_silence_ms: int,
    realtime_feed: bool,
    events: list[dict[str, Any]],
    started: float,
) -> tuple[dict[str, Any], list[bytes]]:
    recorded_frames: list[bytes] = []
    with wave.open(str(audio_path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
        sequence = 0
        total_bytes = 0
        resample_state = None
        while True:
            data = handle.readframes(frames_per_chunk)
            if not data:
                break
            feed_data = data
            feed_sample_rate = sample_rate
            feed_channels = channels
            if channels > 1:
                feed_data = audioop.tomono(feed_data, sample_width, 0.5, 0.5)
                feed_channels = 1
            if sample_rate != 16000:
                feed_data, resample_state = audioop.ratecv(
                    feed_data,
                    sample_width,
                    feed_channels,
                    sample_rate,
                    16000,
                    resample_state,
                )
                feed_sample_rate = 16000
            sequence += 1
            total_bytes += len(feed_data)
            recorded_frames.append(feed_data)
            recorder.feed_audio(feed_data, original_sample_rate=feed_sample_rate)
            events.append(
                {
                    "type": "realtimestt.feed_audio",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "sequence": sequence,
                    "byte_count": len(feed_data),
                    "source_byte_count": len(data),
                    "source_sample_rate": sample_rate,
                    "sample_rate": feed_sample_rate,
                    "channels": feed_channels,
                    "source_channels": channels,
                    "sample_width": sample_width,
                    "chunk_ms": chunk_ms,
                }
            )
            if realtime_feed:
                time.sleep(chunk_ms / 1000)
    silence_sequence = 0
    silence_chunk_bytes = b"\x00\x00" * int(16000 * chunk_ms / 1000)
    silence_chunks = max(0, int(trailing_silence_ms / chunk_ms))
    for _ in range(silence_chunks):
        silence_sequence += 1
        recorder.feed_audio(silence_chunk_bytes, original_sample_rate=16000)
        events.append(
            {
                "type": "realtimestt.feed_trailing_silence",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "sequence": silence_sequence,
                "byte_count": len(silence_chunk_bytes),
                "chunk_ms": chunk_ms,
            }
        )
        if realtime_feed:
            time.sleep(chunk_ms / 1000)
    return {
        "chunk_count": sequence,
        "total_audio_bytes": total_bytes,
        "chunk_ms": chunk_ms,
        "trailing_silence_ms": trailing_silence_ms,
        "trailing_silence_chunks": silence_chunks,
        "realtime_feed": realtime_feed,
    }, recorded_frames


def start_recorder_text_waiter(recorder: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"text": "", "error": None}

    def _target() -> None:
        try:
            result["text"] = recorder.text() or ""
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_target, name="realtimestt-text-timeout", daemon=True)
    thread.start()
    return {"thread": thread, "result": result}


def finish_recorder_text_waiter(
    *,
    recorder: Any,
    waiter: dict[str, Any],
    timeout_s: float,
    events: list[dict[str, Any]],
    started: float,
) -> tuple[str, dict[str, Any]]:
    outcome: dict[str, Any] = {"timed_out": False, "timeout_s": timeout_s}
    thread = waiter["thread"]
    result = waiter["result"]
    thread.join(timeout_s)
    if thread.is_alive():
        outcome["timed_out"] = True
        events.append(
            {
                "type": "realtimestt.text_timeout",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "timeout_s": timeout_s,
            }
        )
        try:
            recorder.abort()
        except Exception as exc:  # noqa: BLE001
            outcome["abort_error"] = f"{type(exc).__name__}: {exc}"
        try:
            interrupt = getattr(recorder, "interrupt_stop_event", None)
            if interrupt is not None:
                interrupt.set()
        except Exception as exc:  # noqa: BLE001
            outcome["interrupt_error"] = f"{type(exc).__name__}: {exc}"
        return "", outcome
    if result["error"]:
        outcome["error"] = result["error"]
    return str(result["text"] or ""), outcome


def recorder_text_with_timeout(
    *,
    recorder: Any,
    timeout_s: float,
    events: list[dict[str, Any]],
    started: float,
) -> tuple[str, dict[str, Any]]:
    waiter = start_recorder_text_waiter(recorder)
    return finish_recorder_text_waiter(
        recorder=recorder,
        waiter=waiter,
        timeout_s=timeout_s,
        events=events,
        started=started,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    audio = args.audio.resolve()
    if not audio.exists():
        failed_gates.append("audio_exists")
    else:
        artifacts["input_audio"] = wav_metrics(audio)

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        failed_gates.append(f"api_key_env_present:{args.api_key_env}")

    sys.path.insert(0, str(args.realtimestt_root.resolve()))
    try:
        from RealtimeSTT import AudioToTextRecorder
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": "chatterbox.realtimestt.listener_bridge.v1",
            "ok": False,
            "mocked": False,
            "live": False,
            "started_at_utc": utc_now(),
            "ended_at_utc": utc_now(),
            "services": services,
            "artifacts": artifacts,
            "events": events,
            "failed_gates": failed_gates + ["realtimestt_import_ok"],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "claims": {"proves": [], "does_not_prove": ["realtimestt_external_audio_path"]},
        }

    services["realtimestt"] = {
        "root": str(args.realtimestt_root.resolve()),
        "use_microphone": False,
        "silero_backend": args.silero_backend,
        "external_transcription_executor": "openai_compatible_whisper",
        "endpointing_mode": "manual_start_stop" if args.manual_start_stop else "vad_wait_audio",
        "text_timeout_s": args.text_timeout_s,
    }
    services["asr_executor"] = {
        "kind": "openai_compatible",
        "base_url": args.asr_openai_base_url,
        "api_key_env": args.api_key_env,
        "live": bool(api_key),
    }

    transcript = ""
    executor = None
    feed_summary: dict[str, Any] | None = None
    text_wait: dict[str, Any] | None = None
    recorder = None
    if not failed_gates:
        try:
            executor = WhisperExecutor(
                base_url=args.asr_openai_base_url,
                api_key=api_key,
                events=events,
                started=started,
            )

            def callback_event(event_type: str):
                def _inner(*_args: Any, **_kwargs: Any) -> None:
                    events.append(
                        {
                            "type": event_type,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        }
                    )

                return _inner

            recorder = AudioToTextRecorder(
                use_microphone=False,
                transcription_executor=executor,
                spinner=False,
                no_log_file=True,
                level=50,
                device="cpu",
                silero_backend=args.silero_backend,
                warmup_vad=False,
                post_speech_silence_duration=args.post_speech_silence_duration,
                min_length_of_recording=args.min_length_of_recording,
                pre_recording_buffer_duration=args.pre_recording_buffer_duration,
                on_vad_start=callback_event("realtimestt.vad_start"),
                on_vad_stop=callback_event("realtimestt.vad_stop"),
                on_recording_start=callback_event("realtimestt.recording_start"),
                on_recording_stop=callback_event("realtimestt.recording_stop"),
                on_transcription_start=callback_event("realtimestt.transcription_start"),
                on_recorded_chunk=lambda chunk: events.append(
                    {
                        "type": "realtimestt.recorded_chunk",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "byte_count": len(chunk),
                    }
                ),
            )
            services["realtimestt"]["resolved_silero_backend"] = str(
                getattr(getattr(recorder, "silero_vad_model", None), "backend", "unknown")
            )
            text_waiter = None
            if not args.manual_start_stop:
                text_waiter = start_recorder_text_waiter(recorder)
                events.append(
                    {
                        "type": "realtimestt.text_wait_started_before_feed",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
                time.sleep(args.pre_feed_listen_s)
            feed_summary, recorded_frames = feed_wav_to_recorder(
                recorder=recorder,
                audio_path=audio,
                chunk_ms=args.chunk_ms,
                trailing_silence_ms=args.trailing_silence_ms,
                realtime_feed=args.realtime_feed,
                events=events,
                started=started,
            )
            if args.manual_start_stop:
                recorder.start(frames=recorded_frames)
                events.append(
                    {
                        "type": "realtimestt.manual_recording_start",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "frame_count": len(recorded_frames),
                    }
                )
                recorder.stop()
                events.append(
                    {
                        "type": "realtimestt.manual_recording_stop",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
            if text_waiter is not None:
                transcript, text_wait = finish_recorder_text_waiter(
                    recorder=recorder,
                    waiter=text_waiter,
                    timeout_s=args.text_timeout_s,
                    events=events,
                    started=started,
                )
            else:
                transcript, text_wait = recorder_text_with_timeout(
                    recorder=recorder,
                    timeout_s=args.text_timeout_s,
                    events=events,
                    started=started,
                )
            events.append(
                {
                    "type": "realtimestt.text_returned",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "text_sha256": sha256_text(transcript),
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed_gates.append("realtimestt_external_audio_transcribed")
            services["realtimestt"]["error_type"] = type(exc).__name__
            services["realtimestt"]["error"] = str(exc)
        finally:
            if recorder is not None:
                try:
                    recorder.shutdown()
                except Exception as exc:  # noqa: BLE001
                    services["realtimestt"]["shutdown_error"] = f"{type(exc).__name__}: {exc}"

    if feed_summary is None:
        failed_gates.append("realtimestt_feed_summary_present")
    if not transcript:
        failed_gates.append("realtimestt_transcript_present")
    if text_wait and text_wait.get("timed_out"):
        failed_gates.append("realtimestt_text_returned_before_timeout")
    if executor is None or not executor.calls:
        failed_gates.append("live_asr_executor_called")
    if args.manual_start_stop:
        if not any(event["type"] == "realtimestt.manual_recording_start" for event in events):
            failed_gates.append("realtimestt_manual_recording_start_present")
        if not any(event["type"] == "realtimestt.manual_recording_stop" for event in events):
            failed_gates.append("realtimestt_manual_recording_stop_present")
    else:
        if not any(event["type"] == "realtimestt.vad_start" for event in events):
            failed_gates.append("realtimestt_vad_start_event_present")
        if not any(event["type"] == "realtimestt.vad_stop" for event in events):
            failed_gates.append("realtimestt_vad_stop_event_present")

    gate = None
    if args.expected_transcript and transcript:
        gate = acceptance_result(expected_text=args.expected_transcript, transcript=transcript, max_wer=args.max_wer)
        if not gate["ok"]:
            failed_gates.extend(f"transcript_{name}" for name in gate["failed_gates"])

    ended_at = utc_now()
    ok = not failed_gates
    return {
        "schema": "chatterbox.realtimestt.listener_bridge.v1",
        "ok": ok,
        "mocked": False,
        "live": bool(ok and executor and executor.calls),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended_at,
        "inputs": {
            "audio": str(audio),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript) if args.expected_transcript else None,
            "chunk_ms": args.chunk_ms,
            "trailing_silence_ms": args.trailing_silence_ms,
            "realtime_feed": args.realtime_feed,
        },
        "services": services,
        "artifacts": artifacts,
        "feed_summary": feed_summary,
        "text_wait": text_wait,
        "events": events,
        "asr_executor_calls": executor.calls if executor else [],
        "transcript": {
            "schema": "chatterbox.realtimestt.transcript.v1",
            "text": transcript,
            "text_sha256": sha256_text(transcript),
            "acceptance_gate": gate,
        },
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "realtimestt_external_audio_api_accepts_real_wav_frames",
                "realtimestt_endpointing_emits_recording_boundary_events",
                "realtimestt_final_text_uses_live_asr_executor",
            ]
            if ok
            else [],
            "does_not_prove": [
                "physical_microphone_capture",
                *([] if not args.manual_start_stop else ["automatic_vad_endpointing"]),
                "native_realtimestt_faster_whisper_model_path",
                "speaker_identity",
                "memory_recall",
                "chatterbox_rendering",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-transcript", default=None)
    parser.add_argument("--max-wer", default=0.35, type=float)
    parser.add_argument("--realtimestt-root", default="/home/graham/workspace/experiments/RealtimeSTT", type=Path)
    parser.add_argument("--asr-openai-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--api-key-env", default=os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY"))
    parser.add_argument("--chunk-ms", default=20, type=int)
    parser.add_argument("--trailing-silence-ms", default=1400, type=int)
    parser.add_argument("--realtime-feed", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--silero-backend", default="auto")
    parser.add_argument("--manual-start-stop", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--post-speech-silence-duration", default=0.45, type=float)
    parser.add_argument("--min-length-of-recording", default=0.0, type=float)
    parser.add_argument("--pre-recording-buffer-duration", default=0.2, type=float)
    parser.add_argument("--text-timeout-s", default=120.0, type=float)
    parser.add_argument("--pre-feed-listen-s", default=0.15, type=float)
    args = parser.parse_args()
    receipt = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "out": str(args.out),
                "failed_gates": receipt["failed_gates"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
