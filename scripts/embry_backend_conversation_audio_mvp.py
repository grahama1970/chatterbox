#!/usr/bin/env python3
"""Prove audible backend voice conversation turns without a browser microphone.

Flow:
1. Dynamically render an agent question WAV through SPARTA direct-speak.
2. Route that WAV through the PipeWire virtual source used by RealtimeSTT.
3. Use the RealtimeSTT final transcript as the SPARTA live-turn input.
4. Let SPARTA generate/render Embry's answer through Chatterbox.
5. Play Embry's rendered answer to the configured Jabra sink.
6. Repeat for each requested round.

This is intentionally backend-only. It proves the audio/input/output plumbing
for audible turns and records what it does not prove in the receipt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
EMBRY_VOICE_CONTROL_SKILL_SRC = "/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/src"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from embry_live_asr_capture_mvp import (  # noqa: E402
    DEFAULT_JABRA_SINK,
    VIRTUAL_SOURCE,
    VIRTUAL_SINK,
    resolve_api_key,
    run_cmd,
    run_route,
)
from smoke_realtimestt_listener_bridge import (  # noqa: E402
    sha256_text,
    transcribe_openai_compatible,
    utc_now,
    wav_metrics,
)
from chatterbox.agent.asr_acceptance import normalize_text  # noqa: E402

_local_embry_voice_control_module = sys.modules.pop("embry_voice_control", None)
sys.path.insert(0, EMBRY_VOICE_CONTROL_SKILL_SRC)
from embry_voice_control.listener_turn import publish_listener_turn_journal  # noqa: E402
if _local_embry_voice_control_module is not None:
    sys.modules["embry_voice_control_local"] = _local_embry_voice_control_module


def post_json(url: str, payload: dict[str, Any], timeout_s: float) -> tuple[int | None, dict[str, Any] | None, str | None]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw_body": body[-4000:]}
        return exc.code, parsed, None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"


def compact_voice_envelope(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        return {"present": False}
    frames = envelope.get("frames")
    if not isinstance(frames, list):
        frames = []
    nonzero_level = 0
    nonzero_bass = 0
    nonzero_mid = 0
    nonzero_treble = 0
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        nonzero_level += 1 if float(frame.get("level") or 0) > 0 else 0
        nonzero_bass += 1 if float(frame.get("bass") or 0) > 0 else 0
        nonzero_mid += 1 if float(frame.get("mid") or 0) > 0 else 0
        nonzero_treble += 1 if float(frame.get("treble") or 0) > 0 else 0
    return {
        "present": True,
        "sampleRate": envelope.get("sampleRate"),
        "frameMs": envelope.get("frameMs"),
        "durationMs": envelope.get("durationMs"),
        "stats": envelope.get("stats"),
        "frame_count": len(frames),
        "nonzero_level_frames": nonzero_level,
        "nonzero_bass_frames": nonzero_bass,
        "nonzero_mid_frames": nonzero_mid,
        "nonzero_treble_frames": nonzero_treble,
    }


def existing_audio_metrics(value: Any) -> tuple[str, dict[str, Any]]:
    raw_path = str(value or "").strip()
    if not raw_path:
        return "", {"exists": False, "path": ""}
    path = Path(raw_path)
    if not path.is_file():
        return raw_path, {"exists": False, "path": raw_path}
    return raw_path, wav_metrics(path)


def require_contains(text: str, required: list[str]) -> list[str]:
    normalized = normalize_text(text)
    return [needle for needle in required if normalize_text(needle) not in normalized]


def final_transcript_text(value: Any) -> str:
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    return value if isinstance(value, str) else ""


def render_question(args: argparse.Namespace, out_dir: Path, session_id: str, *, question: str, turn_id: str) -> dict[str, Any]:
    payload = {
        "text": question,
        "tone": "calm_precise",
        "deliveryStage": "neutral",
        "playLocal": False,
        "source": "embry-backend-conversation-agent-question",
        "turnId": turn_id,
        "sessionId": session_id,
    }
    status_code, response, error = post_json(
        f"{args.sparta_api.rstrip('/')}/api/projects/embry-voice/direct-speak",
        payload,
        args.sparta_timeout_s,
    )
    raw_path = out_dir / "agent_question_direct_speak.json"
    raw_path.write_text(json.dumps(response or {"error": error}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audio_path, audio_metrics = existing_audio_metrics((response or {}).get("audioPath"))
    return {
        "request": payload,
        "status_code": status_code,
        "error": error,
        "response_path": str(raw_path),
        "status": (response or {}).get("status"),
        "audio_path": audio_path,
        "receipt_path": (response or {}).get("receiptPath"),
        "audio_metrics": audio_metrics,
        "voice_envelope": compact_voice_envelope((response or {}).get("voiceEnvelope")),
        "ok": bool(status_code == 200 and (response or {}).get("status") == "ok" and audio_metrics.get("exists")),
    }


def sparta_live_turn(args: argparse.Namespace, out_dir: Path, *, transcript: str, session_id: str, turn_id: str) -> dict[str, Any]:
    payload = {
        "text": transcript,
        "sessionId": session_id,
        "turnId": turn_id,
        "inputMode": "voice",
        "inputAuthority": {
            "source": "unix_pipewire_virtual_source_realtimestt",
            "virtual_sink": VIRTUAL_SINK,
            "virtual_source": VIRTUAL_SOURCE,
        },
    }
    status_code, response, error = post_json(
        f"{args.sparta_api.rstrip('/')}/api/projects/embry-voice/live-turn",
        payload,
        args.sparta_timeout_s,
    )
    raw_path = out_dir / "sparta_live_turn.json"
    raw_path.write_text(json.dumps(response or {"error": error}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audio_path, audio_metrics = existing_audio_metrics((response or {}).get("audioPath"))
    memory = (response or {}).get("memory") if isinstance(response, dict) else {}
    memory = memory if isinstance(memory, dict) else {}
    memory_answer = memory.get("answer") if isinstance(memory.get("answer"), dict) else {}
    memory_intent = memory.get("intent") if isinstance(memory.get("intent"), dict) else {}
    return {
        "request": payload,
        "status_code": status_code,
        "error": error,
        "response_path": str(raw_path),
        "status": (response or {}).get("status"),
        "answer_authority": (response or {}).get("answerAuthority"),
        "answer_text": (response or {}).get("answerText"),
        "answer_text_sha256": sha256_text(str((response or {}).get("answerText") or "")),
        "audio_path": audio_path,
        "audio_url": (response or {}).get("audioUrl"),
        "receipt_path": (response or {}).get("receiptPath"),
        "audio_metrics": audio_metrics,
        "voice_envelope": compact_voice_envelope((response or {}).get("voiceEnvelope")),
        "memory_intent": {
            "action": memory_intent.get("action"),
            "query_type": memory_intent.get("query_type"),
            "response_mode": memory_intent.get("response_mode"),
        },
        "memory_answer": {
            "ok": memory_answer.get("ok"),
            "can_answer": memory_answer.get("can_answer"),
            "answer_type": memory_answer.get("answer_type"),
            "session_context_authority": memory_answer.get("session_context_authority"),
            "story_turn_id": memory_answer.get("story_turn_id"),
            "story_context_recovered": memory_answer.get("story_context_recovered"),
            "answer_uses_story_fact": memory_answer.get("answer_uses_story_fact"),
            "final_response_origin": memory_answer.get("final_response_origin"),
            "fallback_used": memory_answer.get("fallback_used"),
            "source_answer_sha256": sha256_text(str(memory_answer.get("source_answer") or "")),
            "final_response_sha256": sha256_text(str(memory_answer.get("final_response") or "")),
            "story_context": memory_answer.get("story_context"),
        },
        "tau_boundary": (response or {}).get("tauBoundary"),
        "unverified": (response or {}).get("unverified"),
        "ok": bool(
            status_code == 200
            and (response or {}).get("status") == "ok"
            and (response or {}).get("answerText")
            and (response or {}).get("answerAuthority") not in (None, "", "none")
            and audio_metrics.get("exists")
        ),
    }


def build_route_args(args: argparse.Namespace, out_dir: Path, source_wav: Path) -> argparse.Namespace:
    return argparse.Namespace(
        source_wav=str(source_wav),
        out_dir=str(out_dir),
        path="virtual",
        jabra_sink=args.jabra_sink,
        jabra_source=args.jabra_source,
        alsa_card=args.alsa_card,
        no_jabra_mirror=args.no_jabra_mirror,
        record_rate=args.record_rate,
        lead_in_s=args.lead_in_s,
        tail_s=args.tail_s,
        record_timeout_s=args.record_timeout_s,
        require_substring=args.require_substring,
        max_wer=args.max_wer,
        whisper_base_url=args.whisper_base_url,
        whisper_container=args.whisper_container,
        whisper_key_path=args.whisper_key_path,
        api_key_env=args.api_key_env,
        realtimestt=True,
        realtimestt_root=args.realtimestt_root,
        realtimestt_python=args.realtimestt_python,
        realtimestt_timeout_s=args.realtimestt_timeout_s,
    )


def derived_required_substrings(args: argparse.Namespace, question: str) -> list[str]:
    if args.require_substring:
        return list(args.require_substring)
    normalized = normalize_text(question)
    required = ["capital"] if "capital" in normalized else []
    for country in ("france", "germany", "italy", "spain", "canada", "japan"):
        if country in normalized:
            required.append(country)
            break
    for content_word in ("cat", "story", "find"):
        if content_word in normalized:
            required.append(content_word)
    return required or ["embry"]


def validate_cat_story_turn(turn_index: int, sparta_turn: dict[str, Any]) -> list[str]:
    failed_gates: list[str] = []
    memory_answer = sparta_turn.get("memory_answer") if isinstance(sparta_turn.get("memory_answer"), dict) else {}
    answer_text = str(sparta_turn.get("answer_text") or "")
    if sparta_turn.get("answer_authority") != "memory":
        failed_gates.append("cat_story_answer_authority_is_memory")
    if memory_answer.get("fallback_used"):
        failed_gates.append("cat_story_memory_fallback_not_used")
    if turn_index == 1:
        if memory_answer.get("answer_type") != "session_story_generation":
            failed_gates.append("cat_story_turn_001_answer_type_session_story_generation")
        if memory_answer.get("session_context_authority") != "memory":
            failed_gates.append("cat_story_turn_001_session_context_authority_memory")
        if not str(memory_answer.get("story_turn_id") or "").strip():
            failed_gates.append("cat_story_turn_001_story_turn_id_present")
        normalized_answer = normalize_text(answer_text)
        if "cat" not in normalized_answer:
            failed_gates.append("cat_story_turn_001_answer_mentions_cat")
        if "?" not in answer_text:
            failed_gates.append("cat_story_turn_001_answer_asks_question")
    elif turn_index == 2:
        if memory_answer.get("answer_type") != "session_story_context":
            failed_gates.append("cat_story_turn_002_answer_type_session_story_context")
        if memory_answer.get("story_context_recovered") is not True:
            failed_gates.append("cat_story_turn_002_story_context_recovered")
        if memory_answer.get("answer_uses_story_fact") is not True:
            failed_gates.append("cat_story_turn_002_answer_uses_story_fact")
        if not answer_text.strip():
            failed_gates.append("cat_story_turn_002_answer_text_present")
    return failed_gates


def execute_turn(
    *,
    args: argparse.Namespace,
    out_dir: Path,
    session_id: str,
    turn_index: int,
    question: str,
    api_key: str,
) -> tuple[dict[str, Any], list[str]]:
    turn_dir = out_dir / f"turn-{turn_index:03d}"
    turn_dir.mkdir(parents=True, exist_ok=True)
    turn_failed_gates: list[str] = []
    required_substrings = derived_required_substrings(args, question)
    turn_args = argparse.Namespace(**vars(args))
    turn_args.question = question
    turn_args.require_substring = required_substrings

    turn: dict[str, Any] = {
        "turn_index": turn_index,
        "question": question,
        "required_substrings": required_substrings,
        "out_dir": str(turn_dir),
        "mocked": False,
        "live": True,
        "failed_gates": turn_failed_gates,
    }

    question_render = render_question(
        turn_args,
        turn_dir,
        session_id,
        question=question,
        turn_id=f"{session_id}:turn-{turn_index:03d}:agent-question-render",
    )
    turn["agent_question_render"] = question_render
    if not question_render["ok"]:
        turn_failed_gates.append("agent_question_direct_speak_ok")
        turn["pass"] = False
        return turn, turn_failed_gates

    source_wav = Path(question_render["audio_path"])
    try:
        source_transcript = transcribe_openai_compatible(turn_args.whisper_base_url, api_key, source_wav)
    except Exception as exc:  # noqa: BLE001
        source_transcript = ""
        turn["source_transcription_error"] = f"{type(exc).__name__}: {exc}"
        turn_failed_gates.append("source_question_wav_transcription_ok")
    turn["source_transcript"] = source_transcript
    turn["source_transcript_sha256"] = sha256_text(source_transcript)

    route = run_route(
        route="virtual",
        args=build_route_args(turn_args, turn_dir / "virtual-route", source_wav),
        out_dir=turn_dir / "virtual-route",
        source_wav=source_wav,
        source_transcript=source_transcript,
        api_key=api_key,
        required_substrings=required_substrings,
    )
    turn["virtual_realtimestt_route"] = route
    realtime_transcript_payload = (route.get("realtimestt") or {}).get("transcript")
    realtime_transcript = final_transcript_text(realtime_transcript_payload)
    turn["realtimestt_final_transcript"] = realtime_transcript
    turn["realtimestt_final_transcript_payload"] = realtime_transcript_payload
    turn["realtimestt_final_transcript_sha256"] = sha256_text(realtime_transcript)
    missing = require_contains(realtime_transcript, required_substrings)
    if not route.get("pass"):
        turn_failed_gates.append("virtual_pipewire_capture_route_pass")
    if not (route.get("realtimestt") or {}).get("ok"):
        turn_failed_gates.append("realtimestt_final_transcript_ok")
    if missing:
        turn["realtimestt_missing_required_substrings"] = missing
        turn_failed_gates.append("realtimestt_transcript_contains_required_content")

    sparta_turn = sparta_live_turn(
        turn_args,
        turn_dir,
        transcript=realtime_transcript,
        session_id=session_id,
        turn_id=f"{session_id}:turn-{turn_index:03d}:embry-answer",
    )
    turn["sparta_live_turn"] = sparta_turn
    if not sparta_turn["ok"]:
        turn_failed_gates.append("sparta_live_turn_dynamic_answer_and_chatterbox_render_ok")
    if args.cat_story_conversation:
        turn_failed_gates.extend(validate_cat_story_turn(turn_index, sparta_turn))

    playback = {"skipped": True}
    audio_path_raw = str(sparta_turn.get("audio_path") or "").strip()
    audio_path = Path(audio_path_raw) if audio_path_raw else None
    if audio_path and audio_path.is_file():
        playback = run_cmd(["pw-play", "--target", turn_args.jabra_sink, str(audio_path)], timeout=turn_args.playback_timeout_s)
        if playback.get("returncode") != 0:
            turn_failed_gates.append("jabra_answer_playback_returncode_zero")
    else:
        turn_failed_gates.append("jabra_answer_playback_audio_path_exists")
    turn["answer_playback"] = {
        "mocked": False,
        "live": True,
        "driver": "pipewire-pw-play",
        "target": turn_args.jabra_sink,
        **playback,
    }

    if args.publish_journal:
        try:
            sparta_response = json.loads(Path(str(sparta_turn["response_path"])).read_text(encoding="utf-8"))
            listener_receipt = {
                "schema": "embry.backend_conversation_audio_mvp.listener_receipt.v1",
                "mocked": False,
                "live": True,
                "transcript": {"final": realtime_transcript},
                "listener_events": {
                    "final_transcript": realtime_transcript,
                    "normalized_final_transcript": normalize_text(realtime_transcript),
                    "wake_detected": turn_index > 1 or "embry" in normalize_text(realtime_transcript),
                    "events_path": (route.get("realtimestt") or {}).get("events_path"),
                },
                "realtimestt": {
                    "receipt_path": (route.get("realtimestt") or {}).get("receipt_path"),
                    "event_count": (route.get("realtimestt") or {}).get("event_count"),
                },
                "underlying_receipt_path": (route.get("realtimestt") or {}).get("receipt_path"),
                "route_receipt": route,
            }
            listener_receipt_path = turn_dir / "listener_receipt_for_journal.json"
            listener_receipt_path.write_text(json.dumps(listener_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            local_playback = {
                "requested": True,
                "played": playback.get("returncode") == 0,
                "command": ["pw-play", "--target", turn_args.jabra_sink, str(audio_path)] if audio_path else [],
                "driver": "pipewire-pw-play",
                "target": turn_args.jabra_sink,
                "returncode": playback.get("returncode"),
            }
            journal_events = publish_listener_turn_journal(
                journal_db=Path(args.journal_db),
                receipt_created_at=utc_now(),
                listener_receipt_path=listener_receipt_path,
                listener_receipt=listener_receipt,
                turn_text=realtime_transcript,
                request_payload=sparta_response.get("turnAuthority") if isinstance(sparta_response.get("turnAuthority"), dict) else sparta_turn["request"],
                response=sparta_response,
                local_playback=local_playback,
            )
            turn["journal_publish"] = {
                "mocked": False,
                "live": True,
                "journal_db": args.journal_db,
                "event_count": len(journal_events),
                "event_types": [event.get("type") for event in journal_events],
                "last_sequence": journal_events[-1].get("sequence") if journal_events else None,
            }
        except Exception as exc:  # noqa: BLE001
            turn["journal_publish"] = {
                "mocked": False,
                "live": True,
                "journal_db": args.journal_db,
                "error": f"{type(exc).__name__}: {exc}",
            }
            turn_failed_gates.append("journal_publish_for_ui_projection_ok")

    question_envelope = question_render["voice_envelope"]
    answer_envelope = sparta_turn["voice_envelope"]
    if not question_envelope.get("present") or question_envelope.get("nonzero_level_frames", 0) <= 0:
        turn_failed_gates.append("agent_question_voice_envelope_has_nonzero_frames")
    if not answer_envelope.get("present") or answer_envelope.get("nonzero_level_frames", 0) <= 0:
        turn_failed_gates.append("embry_answer_voice_envelope_has_nonzero_frames")
    if answer_envelope.get("nonzero_bass_frames", 0) <= 0 or answer_envelope.get("nonzero_mid_frames", 0) <= 0:
        turn_failed_gates.append("embry_answer_voice_envelope_frequency_bands_nonzero")

    turn["pass"] = not turn_failed_gates
    return turn, turn_failed_gates


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    session_id = args.session_id or f"embry-backend-conversation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    failed_gates: list[str] = []
    questions = list(args.question)

    receipt: dict[str, Any] = {
        "schema": "embry.backend_conversation_audio_mvp.v1",
        "mocked": False,
        "live": True,
        "started_at_utc": utc_now(),
        "out_dir": str(out_dir),
        "session_id": session_id,
        "round_count": len(questions),
        "questions": questions,
        "turns": [],
        "failed_gates": failed_gates,
        "claims": {
            "proves": [],
            "does_not_prove": [
                "browser_webrtc_microphone",
                "physical_jabra_microphone_capture",
                "openwakeword_detection",
                "distinct_second_agent_voice_identity",
                "orb_cdp_animation",
                "fully_autonomous_dialogue_planning",
            ],
        },
    }

    key_info = resolve_api_key(args)
    receipt["whisper"] = {
        "base_url": args.whisper_base_url,
        "container": args.whisper_container,
        "api_key_present": key_info["present"],
        "api_key_source": key_info["source"],
    }
    if not key_info["present"]:
        failed_gates.append("whisper_api_key_available")
        receipt["pass"] = False
        receipt["ended_at_utc"] = utc_now()
        return receipt

    for index, question in enumerate(questions, start=1):
        turn, turn_failed = execute_turn(
            args=args,
            out_dir=out_dir,
            session_id=session_id,
            turn_index=index,
            question=question,
            api_key=key_info["value"],
        )
        receipt["turns"].append(turn)
        failed_gates.extend([f"turn_{index:03d}:{gate}" for gate in turn_failed])

    receipt["pass"] = not failed_gates
    if receipt["pass"]:
        receipt["claims"]["proves"] = [
            "multi_round_dynamic_agent_question_wavs_rendered_by_chatterbox",
            "each_round_virtual_pipewire_source_reaches_realtimestt_final_transcript",
            "each_round_realtimestt_final_transcript_drives_sparta_live_turn",
            "each_round_sparta_live_turn_returns_dynamic_answer_authority",
            "each_round_sparta_live_turn_renders_embry_answer_with_chatterbox",
            "each_round_embry_answer_wav_played_to_jabra_sink",
            "each_round_answer_voice_envelope_contains_nonzero_level_and_frequency_frames",
        ]
    if len(receipt["turns"]) == 1:
        only_turn = receipt["turns"][0]
        receipt["question"] = only_turn["question"]
        for key in (
            "agent_question_render",
            "source_transcript",
            "source_transcript_sha256",
            "virtual_realtimestt_route",
            "realtimestt_final_transcript",
            "realtimestt_final_transcript_payload",
            "realtimestt_final_transcript_sha256",
            "sparta_live_turn",
            "answer_playback",
        ):
            if key in only_turn:
                receipt[key] = only_turn[key]
    receipt["ended_at_utc"] = utc_now()
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--question", action="append", default=None)
    parser.add_argument("--cat-story-conversation", action="store_true")
    parser.add_argument("--publish-journal", action="store_true")
    parser.add_argument("--journal-db", default="/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--sparta-api", default=os.getenv("SPARTA_API", "http://127.0.0.1:3001"))
    parser.add_argument("--sparta-timeout-s", type=float, default=90.0)
    parser.add_argument("--jabra-sink", default=DEFAULT_JABRA_SINK)
    parser.add_argument("--jabra-source", default="alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback")
    parser.add_argument("--alsa-card", default="Jabra")
    parser.add_argument("--no-jabra-mirror", action="store_true")
    parser.add_argument("--record-rate", type=int, default=16000)
    parser.add_argument("--lead-in-s", type=float, default=1.0)
    parser.add_argument("--tail-s", type=float, default=1.0)
    parser.add_argument("--record-timeout-s", type=float, default=90.0)
    parser.add_argument("--playback-timeout-s", type=float, default=90.0)
    parser.add_argument("--require-substring", action="append", default=None)
    parser.add_argument("--max-wer", type=float, default=0.45)
    parser.add_argument("--whisper-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--whisper-container", default="whisper")
    parser.add_argument("--whisper-key-path", default="/var/lib/whisper/.api_key")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--realtimestt-root", default="/home/graham/workspace/experiments/RealtimeSTT")
    parser.add_argument("--realtimestt-python", default="/home/graham/workspace/experiments/RealtimeSTT/.venv-fastapi/bin/python")
    parser.add_argument("--realtimestt-timeout-s", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.question is None:
        if args.cat_story_conversation:
            args.question = [
                "Hey Embry, tell me a short story about your cat and ask me one question about it.",
                "What did the cat find?",
            ]
        else:
            args.question = [
                "Hey Embry, what is the capital of France?",
                "What is the capital of Germany?",
            ]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = build_receipt(args)
    out_path = Path(args.out_dir).resolve() / "summary.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pass": receipt["pass"], "mocked": False, "live": True, "out": str(out_path), "failed_gates": receipt["failed_gates"]}, sort_keys=True))
    return 0 if receipt["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
