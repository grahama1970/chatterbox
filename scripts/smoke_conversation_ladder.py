#!/usr/bin/env python3
"""Run live, non-mocked Chatterbox conversation sanity ladder rungs.

Only rung 1 is implemented initially. It proves a file-backed listener input can
drive one real ASR -> Chatterbox TTS -> ASR verification loop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.asr_acceptance import acceptance_result


RUNG1_SCHEMA = "chatterbox.conversation_ladder.rung1.v1"
RUNG2_SCHEMA = "chatterbox.conversation_ladder.rung2.v1"
DEFAULT_RESPONSE_TEXT = "Hello. I am listening."


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


def parse_path_maps(values: list[str]) -> dict[str, Path]:
    mappings: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"path map must use SOURCE=TARGET: {value}")
        source, target = value.split("=", 1)
        source = source.rstrip("/")
        if not source or not target:
            raise ValueError(f"path map must use non-empty SOURCE=TARGET: {value}")
        mappings[source] = Path(target)
    return mappings


def apply_path_maps(path: Path, path_maps: dict[str, Path]) -> Path:
    path_text = str(path)
    for source, target in sorted(path_maps.items(), key=lambda item: len(item[0]), reverse=True):
        if path_text == source or path_text.startswith(f"{source}/"):
            return target / path_text[len(source) :].lstrip("/")
    return path


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = get_json(f"{base_url.rstrip('/')}/health", timeout=10)
            if health.get("ok"):
                return health
            last_error = f"health_not_ok:{health}"
        except (ConnectionResetError, TimeoutError, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def load_faster_whisper(model_name: str, device: str, compute_type: str) -> tuple[Any | None, str | None]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001 - reported in receipt
        return None, f"{type(exc).__name__}: {exc}"
    return WhisperModel(model_name, device=device, compute_type=compute_type), None


def transcribe_faster_whisper(model: Any, audio_path: Path) -> str:
    segments, _info = model.transcribe(str(audio_path), beam_size=1, vad_filter=False)
    return " ".join(segment.text.strip() for segment in segments).strip()


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
    data = response.json()
    return str(data.get("text") or "").strip()


def build_asr_backend(args: argparse.Namespace) -> dict[str, Any]:
    if args.asr_openai_base_url:
        api_key = os.getenv(args.api_key_env)
        if not api_key:
            return {
                "kind": "openai_compatible",
                "live": False,
                "error": f"missing_api_key_env:{args.api_key_env}",
            }
        return {
            "kind": "openai_compatible",
            "live": True,
            "base_url": args.asr_openai_base_url,
            "api_key_env": args.api_key_env,
            "api_key": api_key,
        }
    model, error = load_faster_whisper(args.asr_model, args.asr_device, args.asr_compute_type)
    return {
        "kind": "faster_whisper",
        "live": model is not None,
        "model_name": args.asr_model,
        "device": args.asr_device,
        "compute_type": args.asr_compute_type,
        "model": model,
        "error": error,
    }


def asr_backend_receipt(backend: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in backend.items()
        if key not in {"api_key", "model"}
    }


def transcribe_audio(backend: dict[str, Any], audio_path: Path) -> str:
    if backend["kind"] == "openai_compatible":
        return transcribe_openai_compatible(str(backend["base_url"]), str(backend["api_key"]), audio_path)
    model = backend.get("model")
    if model is None:
        raise RuntimeError(backend.get("error") or "asr_backend_unavailable")
    return transcribe_faster_whisper(model, audio_path)


def append_event(events: list[dict[str, Any]], started: float, event_type: str, **fields: Any) -> None:
    events.append(
        {
            "sequence": len(events) + 1,
            "type": event_type,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            **fields,
        }
    )


def transcript_gate(
    *,
    backend: dict[str, Any],
    audio_path: Path,
    expected_text: str,
    max_wer: float,
) -> dict[str, Any]:
    transcript = transcribe_audio(backend, audio_path)
    gate = acceptance_result(
        expected_text=expected_text,
        transcript=transcript,
        max_wer=max_wer,
    )
    return {
        "expected_text": expected_text,
        "expected_text_sha256": sha256_text(expected_text),
        "transcript": transcript,
        "gate": gate,
    }


def synthesize_live(
    *,
    base_url: str,
    text: str,
    label: str,
    path_maps: dict[str, Path],
    timeout_s: int,
) -> tuple[dict[str, Any], Path | None, dict[str, Any]]:
    payload = {
        "text": text,
        "label": label,
        "delivery_stage": "neutral",
    }
    synthesis = post_json(f"{base_url}/synthesize", payload, timeout=timeout_s)
    raw_audio = synthesis.get("audio")
    artifact: dict[str, Any] = {"server_path": raw_audio}
    if not raw_audio:
        return synthesis, None, artifact
    output_audio_path = apply_path_maps(Path(str(raw_audio)), path_maps)
    artifact["host_path"] = str(output_audio_path)
    if output_audio_path.exists() and output_audio_path.suffix.lower() == ".wav":
        artifact.update(wav_metrics(output_audio_path))
    return synthesis, output_audio_path, artifact


def extract_favorite_color(transcript: str) -> str | None:
    match = re.search(r"\bfavou?rite color is ([a-z]+)\b", transcript, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    match = re.search(r"\bi like ([a-z]+)\b", transcript, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def route_turn2_from_state(state: dict[str, Any]) -> dict[str, Any]:
    color = ((state.get("facts") or {}).get("favorite_color") or "").strip()
    if not color:
        return {
            "ok": False,
            "route": "local_state_color_recall",
            "failed_gates": ["local_state_favorite_color_present"],
            "response_text": "I do not have that color in this session state.",
        }
    return {
        "ok": True,
        "route": "local_state_color_recall",
        "failed_gates": [],
        "response_text": f"You said your favorite color is {color}.",
        "used_state": {"favorite_color": color},
    }


def run_rung1(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung1-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    services: dict[str, Any] = {}
    health: dict[str, Any] | None = None
    synthesis: dict[str, Any] | None = None
    output_audio_path: Path | None = None
    input_asr: dict[str, Any] | None = None
    output_asr: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=1, run_id=run_id)
    fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("input_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("input_audio_is_wav")
    else:
        artifacts["input_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.input_audio_ready", audio=str(fixture))

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    if fixture.exists() and backend.get("live"):
        try:
            transcript = transcribe_audio(backend, fixture)
            gate = acceptance_result(
                expected_text=args.expected_transcript,
                transcript=transcript,
                max_wer=args.max_input_wer,
            )
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "transcript": transcript,
                "gate": gate,
            }
            append_event(events, started, "asr.input_transcribed", ok=gate["ok"], wer=gate["wer"])
            if not gate["ok"]:
                failed_gates.extend(f"input_asr_{gate_name}" for gate_name in gate["failed_gates"])
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("input_asr_transcribed")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    response_text = args.response_text
    route = {
        "name": "scripted_simple",
        "requires_memory": False,
        "requires_tools": False,
        "response_text": response_text,
        "response_text_sha256": sha256_text(response_text),
    }
    if not response_text.strip():
        failed_gates.append("response_text_non_empty")

    if health and health.get("ok"):
        payload = {
            "text": response_text,
            "label": args.label or run_id,
            "delivery_stage": "neutral",
        }
        append_event(events, started, "tts.request_submitted", route=route["name"])
        try:
            synthesis = post_json(f"{base_url}/synthesize", payload, timeout=args.synthesis_timeout_s)
            append_event(events, started, "tts.response_received", ok=synthesis.get("ok"))
            if not synthesis.get("ok"):
                failed_gates.append("tts_synthesis_ok")
            raw_audio = synthesis.get("audio")
            if raw_audio:
                output_audio_path = apply_path_maps(Path(str(raw_audio)), path_maps)
                artifacts["output_audio"] = {
                    "server_path": raw_audio,
                    "host_path": str(output_audio_path),
                }
                if output_audio_path.exists() and output_audio_path.suffix.lower() == ".wav":
                    artifacts["output_audio"].update(wav_metrics(output_audio_path))
                else:
                    failed_gates.append("output_audio_exists")
            else:
                failed_gates.append("output_audio_path_present")
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            synthesis = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("tts_synthesis_response")

    if output_audio_path and output_audio_path.exists() and backend.get("live"):
        try:
            transcript = transcribe_audio(backend, output_audio_path)
            gate = acceptance_result(
                expected_text=response_text,
                transcript=transcript,
                max_wer=args.max_output_wer,
            )
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "transcript": transcript,
                "gate": gate,
            }
            append_event(events, started, "asr.output_transcribed", ok=gate["ok"], wer=gate["wer"])
            if not gate["ok"]:
                failed_gates.extend(f"output_asr_{gate_name}" for gate_name in gate["failed_gates"])
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("output_asr_transcribed")
    elif output_audio_path and not backend.get("live"):
        failed_gates.append("output_asr_backend_available")

    ended_at = utc_now()
    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG1_SCHEMA,
        "ok": not failed_gates,
        "rung": 1,
        "run_id": run_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and synthesis and synthesis.get("ok")),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended_at,
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript),
            "fixture_provenance": args.fixture_provenance,
        },
        "route": route,
        "events": events,
        "artifacts": artifacts,
        "input_asr": input_asr,
        "synthesis": synthesis,
        "output_asr": output_asr,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "file_backed_listener_input_can_drive_one_real_asr_tts_loop",
                "generated_response_audio_is_asr_verifiable",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "live_microphone_capture",
                "multi_turn_context",
                "memory_correctness",
                "tool_use",
                "emotional_steering_quality",
            ],
        },
    }


def run_rung2(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session_id = args.session_id or f"session-{run_id}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    artifacts: dict[str, Any] = {"turns": []}
    turns: list[dict[str, Any]] = []
    state_snapshots: list[dict[str, Any]] = []
    state: dict[str, Any] = {"facts": {}}

    append_event(events, started, "rung.started", rung=2, run_id=run_id, session_id=session_id)
    if not args.turn1_fixture or not args.turn2_fixture:
        failed_gates.append("turn_fixtures_present")
    if not args.expected_turn1_transcript or not args.expected_turn2_transcript:
        failed_gates.append("expected_turn_transcripts_present")

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    turn_specs = [
        {
            "index": 1,
            "turn_id": f"{run_id}-turn-1",
            "fixture": args.turn1_fixture,
            "expected_transcript": args.expected_turn1_transcript,
            "response_text": None,
        },
        {
            "index": 2,
            "turn_id": f"{run_id}-turn-2",
            "fixture": args.turn2_fixture,
            "expected_transcript": args.expected_turn2_transcript,
            "response_text": None,
        },
    ]

    for spec in turn_specs:
        turn_failed: list[str] = []
        fixture = Path(spec["fixture"]).resolve()
        state_before = json.loads(json.dumps(state))
        turn: dict[str, Any] = {
            "turn_index": spec["index"],
            "turn_id": spec["turn_id"],
            "session_id": session_id,
            "input_audio": {"path": str(fixture), "exists": fixture.exists()},
            "state_before": state_before,
        }
        append_event(events, started, "listener.input_audio_ready", turn_id=spec["turn_id"], audio=str(fixture))
        if not fixture.exists():
            turn_failed.append("input_audio_exists")
        elif fixture.suffix.lower() != ".wav":
            turn_failed.append("input_audio_is_wav")
        else:
            turn["input_audio"].update(wav_metrics(fixture))

        if fixture.exists() and backend.get("live"):
            try:
                asr = transcript_gate(
                    backend=backend,
                    audio_path=fixture,
                    expected_text=str(spec["expected_transcript"]),
                    max_wer=args.max_input_wer,
                )
                turn["input_asr"] = asr
                append_event(
                    events,
                    started,
                    "asr.input_transcribed",
                    turn_id=spec["turn_id"],
                    ok=asr["gate"]["ok"],
                    wer=asr["gate"]["wer"],
                )
                if not asr["gate"]["ok"]:
                    turn_failed.extend(f"input_asr_{gate}" for gate in asr["gate"]["failed_gates"])
            except Exception as exc:  # noqa: BLE001
                turn["input_asr"] = {
                    "expected_text": spec["expected_transcript"],
                    "expected_text_sha256": sha256_text(str(spec["expected_transcript"])),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                turn_failed.append("input_asr_transcribed")

        transcript = ((turn.get("input_asr") or {}).get("transcript") or "").strip()
        if spec["index"] == 1:
            color = extract_favorite_color(transcript)
            if not color:
                turn_failed.append("local_state_favorite_color_extracted")
                color = "unknown"
            else:
                state["facts"]["favorite_color"] = color
            response_text = (
                f"I will remember that your favorite color is {color} for this session."
                if color != "unknown"
                else "I did not catch the favorite color clearly."
            )
            turn["route"] = {
                "name": "local_state_color_capture",
                "extracted": {"favorite_color": None if color == "unknown" else color},
                "requires_memory": False,
                "requires_tools": False,
            }
        else:
            route = route_turn2_from_state(state)
            turn["route"] = {
                "name": route["route"],
                "requires_memory": False,
                "requires_tools": False,
                "used_state": route.get("used_state"),
            }
            if not route["ok"]:
                turn_failed.extend(route["failed_gates"])
            response_text = route["response_text"]

        turn["response_text"] = response_text
        turn["response_text_sha256"] = sha256_text(response_text)
        if health and health.get("ok"):
            append_event(events, started, "tts.request_submitted", turn_id=spec["turn_id"])
            try:
                synthesis, output_audio_path, output_artifact = synthesize_live(
                    base_url=base_url,
                    text=response_text,
                    label=f"{run_id}_turn_{spec['index']}",
                    path_maps=path_maps,
                    timeout_s=args.synthesis_timeout_s,
                )
                turn["synthesis"] = synthesis
                turn["output_audio"] = output_artifact
                append_event(
                    events,
                    started,
                    "tts.response_received",
                    turn_id=spec["turn_id"],
                    ok=synthesis.get("ok"),
                )
                if not synthesis.get("ok"):
                    turn_failed.append("tts_synthesis_ok")
                if output_audio_path is None or not output_audio_path.exists():
                    turn_failed.append("output_audio_exists")
                elif backend.get("live"):
                    try:
                        output_asr = transcript_gate(
                            backend=backend,
                            audio_path=output_audio_path,
                            expected_text=response_text,
                            max_wer=args.max_output_wer,
                        )
                        turn["output_asr"] = output_asr
                        append_event(
                            events,
                            started,
                            "asr.output_transcribed",
                            turn_id=spec["turn_id"],
                            ok=output_asr["gate"]["ok"],
                            wer=output_asr["gate"]["wer"],
                        )
                        if not output_asr["gate"]["ok"]:
                            turn_failed.extend(f"output_asr_{gate}" for gate in output_asr["gate"]["failed_gates"])
                    except Exception as exc:  # noqa: BLE001
                        turn["output_asr"] = {
                            "expected_text": response_text,
                            "expected_text_sha256": sha256_text(response_text),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                        turn_failed.append("output_asr_transcribed")
            except Exception as exc:  # noqa: BLE001
                turn["synthesis"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
                turn_failed.append("tts_synthesis_response")

        turn["state_after"] = json.loads(json.dumps(state))
        turn["failed_gates"] = turn_failed
        state_snapshots.append(
            {
                "turn_id": spec["turn_id"],
                "before": state_before,
                "after": turn["state_after"],
            }
        )
        failed_gates.extend(f"turn_{spec['index']}_{gate}" for gate in turn_failed)
        turns.append(turn)
        artifacts["turns"].append(
            {
                "turn_id": spec["turn_id"],
                "input_audio": turn.get("input_audio"),
                "output_audio": turn.get("output_audio"),
            }
        )

    omitted_turn1_route = route_turn2_from_state({"facts": {}})
    omitted_turn1_gate = {
        "ok": not omitted_turn1_route["ok"],
        "route": omitted_turn1_route,
        "proves_fail_closed_without_turn1_state": not omitted_turn1_route["ok"],
    }
    if omitted_turn1_route["ok"]:
        failed_gates.append("turn2_fails_closed_without_turn1_state")

    if turns and len({turn["session_id"] for turn in turns}) != 1:
        failed_gates.append("stable_session_id")
    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        failed_gates.append("monotonic_event_sequence")
    if (state.get("facts") or {}).get("favorite_color") != "blue":
        failed_gates.append("state_favorite_color_blue")

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG2_SCHEMA,
        "ok": not failed_gates,
        "rung": 2,
        "run_id": run_id,
        "session_id": session_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "turn1_fixture": str(Path(args.turn1_fixture).resolve()) if args.turn1_fixture else None,
            "turn2_fixture": str(Path(args.turn2_fixture).resolve()) if args.turn2_fixture else None,
            "expected_turn1_transcript": args.expected_turn1_transcript,
            "expected_turn2_transcript": args.expected_turn2_transcript,
            "fixture_provenance": args.fixture_provenance,
        },
        "events": events,
        "state_snapshots": state_snapshots,
        "final_state": state,
        "omitted_turn1_gate": omitted_turn1_gate,
        "turns": turns,
        "artifacts": artifacts,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "file_backed_listener_can_run_two_turn_conversation",
                "router_preserves_and_uses_short_local_state",
                "turn2_fails_closed_without_turn1_state",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "long_term_memory_retrieval",
                "dynamic_emotion_adaptation",
                "interruption_during_playback",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rung", type=int, choices=[1, 2], required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--turn1-fixture", type=Path)
    parser.add_argument("--turn2-fixture", type=Path)
    parser.add_argument("--fixture-provenance", default="provided_wav_fixture")
    parser.add_argument("--expected-transcript")
    parser.add_argument("--expected-turn1-transcript")
    parser.add_argument("--expected-turn2-transcript")
    parser.add_argument("--response-text", default=DEFAULT_RESPONSE_TEXT)
    parser.add_argument("--label", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--synthesis-timeout-s", default=300, type=int)
    parser.add_argument("--asr-openai-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL"))
    parser.add_argument("--api-key-env", default=os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY"))
    parser.add_argument("--asr-model", default="small.en")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--asr-compute-type", default="int8")
    parser.add_argument("--max-input-wer", default=0.25, type=float)
    parser.add_argument("--max-output-wer", default=0.35, type=float)
    parser.add_argument(
        "--path-map",
        action="append",
        default=[],
        help="Map receipt audio paths from container to host paths, e.g. /out=/tmp/chatterbox-out.",
    )
    args = parser.parse_args()

    if args.rung == 1:
        if not args.fixture or not args.expected_transcript:
            parser.error("--fixture and --expected-transcript are required for --rung 1")
        receipt = run_rung1(args)
    else:
        if not args.turn1_fixture or not args.turn2_fixture:
            parser.error("--turn1-fixture and --turn2-fixture are required for --rung 2")
        if not args.expected_turn1_transcript or not args.expected_turn2_transcript:
            parser.error("--expected-turn1-transcript and --expected-turn2-transcript are required for --rung 2")
        receipt = run_rung2(args)
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
