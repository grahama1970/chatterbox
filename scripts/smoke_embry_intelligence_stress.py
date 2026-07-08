#!/usr/bin/env python3
"""Stress Embry answerability before voice rendering.

This runner exercises live memory and Brave Search routes, then optionally
renders failed answers through Tau/Chatterbox so bad responses are audible.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BRAVE = Path("/home/graham/workspace/experiments/agent-skills/skills/brave-search/brave_search.py")

CASES: list[dict[str, Any]] = [
    {
        "id": "sparta_qra_acceptance",
        "scope": "sparta_qra",
        "query": "What evidence should a SPARTA QRA include to be acceptable?",
        "kind": "sparta_qra_acceptance",
    },
    {
        "id": "persona_horus_origin",
        "scope": "persona_memory",
        "query": "Where did Horus Lupercal grow up?",
        "kind": "expected_terms",
        "expected_terms": ["cthonia"],
    },
    {
        "id": "persona_private_codeword_miss",
        "scope": "persona_memory",
        "query": "What private code word did I tell Embry yesterday?",
        "kind": "memory_miss",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


def post_json(url: str, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return {
                "ok_http": 200 <= response.status < 300,
                "status_code": response.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "payload": payload,
                "json": json.load(response),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"body": body}
        return {
            "ok_http": False,
            "status_code": exc.code,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "payload": payload,
            "json": parsed,
            "error": f"HTTPError: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 - receipt preserves live transport failures
        return {
            "ok_http": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "payload": payload,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_cmd(cmd: list[str], *, timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
        return {
            "cmd": cmd,
            "returncode": result.returncode,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": result.stdout[-12000:],
            "stderr_tail": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
            "timeout_s": timeout_s,
        }


def answer_text(answer: dict[str, Any]) -> str:
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    return str(payload.get("final_response") or payload.get("source_answer") or "").strip()


def classify_answer(case: dict[str, Any], answer: dict[str, Any]) -> list[str]:
    text = answer_text(answer)
    norm = normalize(text)
    failed: list[str] = []
    if not answer.get("ok_http"):
        failed.append("memory_answer_http_ok")
        return failed
    if case["kind"] == "sparta_qra_acceptance":
        if "s0609" in norm or "deprecated or revoked" in norm or "non generation" in norm:
            failed.append("sparta_qra_answer_overfit_to_unrelated_control_exclusion")
        if not all(term in norm for term in ["qra", "evidence", "acceptable"]):
            failed.append("sparta_qra_answer_missing_acceptance_terms")
    elif case["kind"] == "expected_terms":
        if not all(term in norm for term in case.get("expected_terms", [])):
            failed.append("persona_memory_answer_wrong_or_unrelated")
    elif case["kind"] == "memory_miss":
        payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
        if payload.get("can_answer") is True or bool(text):
            failed.append("memory_miss_should_not_answer_unrelated_record")
    return failed


def answer_sources(answer: dict[str, Any]) -> list[dict[str, Any]]:
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    sources = payload.get("sources")
    return sources if isinstance(sources, list) else []


def has_unrelated_persona_source(answer: dict[str, Any]) -> bool:
    bad_sources = {"skill_descriptions", "sparta_controls"}
    return any(str(source.get("source") or "") in bad_sources for source in answer_sources(answer) if isinstance(source, dict))


def classify_matrix_answer(session: dict[str, Any], answer: dict[str, Any]) -> list[str]:
    text = answer_text(answer)
    norm = normalize(text)
    route = str(session.get("route") or "")
    question = normalize(str(session.get("question") or ""))
    failed: list[str] = []
    if not answer.get("ok_http"):
        return ["memory_answer_http_ok"]
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    if route == "memory.sparta_qra":
        if "s0609" in norm or "deprecated or revoked" in norm or "non generation" in norm:
            failed.append("sparta_qra_answer_overfit_to_unrelated_control_exclusion")
        if "acceptable" in question and not all(term in norm for term in ["qra", "evidence", "acceptable"]):
            failed.append("sparta_qra_answer_missing_acceptance_terms")
        elif not text:
            failed.append("sparta_qra_answer_present")
        elif not any(term in norm for term in ["sparta", "qra", "evidence", "control"]):
            failed.append("sparta_qra_answer_missing_domain_terms")
    elif route == "memory.persona_memory":
        if "where did horus lupercal grow up" in question:
            failed.extend(classify_answer({"kind": "expected_terms", "expected_terms": ["cthonia"]}, answer))
        elif not text:
            failed.append("persona_memory_answer_present")
        if has_unrelated_persona_source(answer):
            failed.append("persona_memory_answer_uses_unrelated_source_collection")
    elif route == "memory.persona_memory.fail_closed":
        if payload.get("can_answer") is True or bool(text):
            failed.append("memory_miss_should_not_answer_unrelated_record")
    else:
        failed.append("runner_route_not_implemented")
    return sorted(set(failed))


def classify_voice_delivery_intent(session: dict[str, Any], intent: dict[str, Any]) -> list[str]:
    if not intent.get("ok_http"):
        return ["memory_intent_http_ok"]
    payload = intent.get("json") if isinstance(intent.get("json"), dict) else {}
    voice_delivery = payload.get("voice_delivery") if isinstance(payload.get("voice_delivery"), dict) else {}
    failed: list[str] = []
    if not voice_delivery:
        return ["voice_delivery_present"]
    if voice_delivery.get("source") != "memory_intent":
        failed.append("voice_delivery_source_memory_intent")
    if not voice_delivery.get("tone"):
        failed.append("voice_delivery_tone_present")
    if not voice_delivery.get("delivery_stage"):
        failed.append("voice_delivery_delivery_stage_present")

    question = normalize(str(session.get("question") or ""))
    tone = normalize(str(voice_delivery.get("tone") or "")).replace(" ", "_")
    expected_by_prompt = [
        (["frustrated", "de_escalate", "warm"], {"neutral_warm", "calm_precise", "careful_concerned", "deflect_calm"}),
        (["hostile", "humorous", "boundary"], {"firm_boundary", "deflect_calm", "playful_light"}),
        (["discouraged", "gently"], {"neutral_warm", "calm_precise", "careful_concerned", "relieved"}),
        (["two", "speakers", "overlap"], {"one_at_a_time_interrupt", "firm_boundary"}),
    ]
    for terms, expected_tones in expected_by_prompt:
        if all(term in question for term in terms) and tone not in expected_tones:
            failed.append(f"voice_delivery_tone_expected_{'_or_'.join(sorted(expected_tones))}")
            break
    return sorted(set(failed))


def run_memory_case(case: dict[str, Any], *, memory_url: str, timeout_s: int) -> dict[str, Any]:
    intent = post_json(
        f"{memory_url.rstrip('/')}/intent",
        {"q": case["query"], "scope": case["scope"], "fast": True},
        timeout_s,
    )
    answer = post_json(
        f"{memory_url.rstrip('/')}/answer",
        {"q": case["query"], "scope": case["scope"], "k": 5},
        timeout_s,
    )
    failed = classify_answer(case, answer)
    return {
        "id": case["id"],
        "query": case["query"],
        "scope": case["scope"],
        "intent": intent,
        "answer": answer,
        "final_response": answer_text(answer),
        "ok": not failed,
        "mocked": False,
        "live": bool(intent.get("ok_http") and answer.get("ok_http")),
        "failed_gates": failed,
    }


def run_brave_query(*, case_id: str, query: str, brave_script: Path, timeout_s: int) -> dict[str, Any]:
    search = run_cmd(
        [
            "python3",
            str(brave_script),
            "web",
            query,
            "--count",
            "5",
            "--json",
        ],
        timeout_s=timeout_s,
    )
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(search.get("stdout_tail") or "{}")
    except json.JSONDecodeError:
        parsed = None
    results = list((parsed or {}).get("results") or [])
    failed: list[str] = []
    if search["returncode"] != 0:
        failed.append("brave_search_command_ok")
    if not results:
        failed.append("brave_search_results_present")
    query_terms = [term for term in normalize(query).split() if len(term) > 4][:4]
    result_text = normalize(" ".join(f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}" for item in results))
    if results and query_terms and not any(term in result_text for term in query_terms):
        failed.append("brave_search_results_relevant")
    return {
        "id": case_id,
        "query": query,
        "brave_search": {**search, "json": parsed},
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": failed,
    }


def run_brave_case(*, brave_script: Path, timeout_s: int) -> dict[str, Any]:
    return run_brave_query(
        case_id="external_brave_search_pyannote",
        query="pyannote audio GitHub overlapped speech detection speaker diarization",
        brave_script=brave_script,
        timeout_s=timeout_s,
    )


def run_matrix_session(
    session: dict[str, Any],
    *,
    memory_url: str,
    brave_script: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    query = str(session.get("question") or "")
    if route == "memory.intent.voice_delivery":
        intent = post_json(
            f"{memory_url.rstrip('/')}/intent",
            {"q": query, "scope": "persona_memory", "fast": True},
            timeout_s,
        )
        failed = classify_voice_delivery_intent(session, intent)
        return {
            "id": session["id"],
            "matrix_session": session,
            "query": query,
            "route": route,
            "intent": intent,
            "voice_delivery": (intent.get("json") or {}).get("voice_delivery") if isinstance(intent.get("json"), dict) else None,
            "ok": not failed,
            "mocked": False,
            "live": bool(intent.get("ok_http")),
            "failed_gates": failed,
        }
    if route.startswith("memory."):
        scope = "sparta_qra" if route == "memory.sparta_qra" else "persona_memory"
        intent = post_json(
            f"{memory_url.rstrip('/')}/intent",
            {"q": query, "scope": scope, "fast": True},
            timeout_s,
        )
        answer = post_json(
            f"{memory_url.rstrip('/')}/answer",
            {"q": query, "scope": scope, "k": 5},
            timeout_s,
        )
        failed = classify_matrix_answer(session, answer)
        return {
            "id": session["id"],
            "matrix_session": session,
            "query": query,
            "route": route,
            "intent": intent,
            "answer": answer,
            "final_response": answer_text(answer),
            "ok": not failed,
            "mocked": False,
            "live": bool(intent.get("ok_http") and answer.get("ok_http")),
            "failed_gates": failed,
        }
    if route == "brave-search.source_receipt":
        result = run_brave_query(
            case_id=str(session["id"]),
            query=query,
            brave_script=brave_script,
            timeout_s=timeout_s,
        )
        result["matrix_session"] = session
        result["route"] = route
        return result
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": query,
        "route": route,
        "ok": False,
        "mocked": False,
        "live": False,
        "failed_gates": ["runner_route_not_implemented"],
    }


def select_matrix_sessions(
    matrix: dict[str, Any],
    *,
    folder: str | None,
    difficulty: str | None,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    sessions = list(matrix.get("sessions") or [])
    if folder:
        sessions = [session for session in sessions if session.get("folder_id") == folder]
    if difficulty:
        sessions = [session for session in sessions if session.get("difficulty") == difficulty]
    sessions = sessions[max(0, offset) :]
    if limit is not None:
        sessions = sessions[:limit]
    return sessions


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def render_spoken_failures(
    *,
    cases: list[dict[str, Any]],
    out_dir: Path,
    playback_sink_target: str,
    timeout_s: int,
    playback_timeout_s: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failed_gates: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        text = str(case.get("final_response") or "").strip()
        if not case.get("failed_gates") or not text:
            continue
        case_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(case["id"])).strip("-")
        receipt = out_dir / f"{case_id}.json"
        wav = out_dir / f"{case_id}.wav"
        render = run_cmd(
            [
                "python3",
                "scripts/smoke_tau_voice_render.py",
                "--out",
                str(receipt),
                "--question",
                str(case["query"]),
                "--answer-text",
                text,
                "--no-use-blessed-qra-cache",
                "--voice-delivery-json",
                json.dumps({"tone": "careful_concerned", "delivery_stage": "failure_audition", "pause_after_ms": 160}),
                "--timeout-s",
                str(timeout_s),
            ],
            timeout_s=timeout_s + 60,
        )
        render_data: dict[str, Any] = {}
        try:
            render_data = json.loads(receipt.read_text(encoding="utf-8"))
        except Exception:
            pass
        source = Path(str(((render_data.get("artifacts") or {}).get("finished_response_audio_host")) or ""))
        copied = source.exists()
        if copied:
            shutil.copy2(source, wav)
        play: dict[str, Any] | None = None
        if copied:
            play = run_cmd(["pw-play", "--target", playback_sink_target, str(wav)], timeout_s=playback_timeout_s)
        case_failed: list[str] = []
        if render["returncode"] != 0 or not render_data.get("ok"):
            case_failed.append("tau_chatterbox_render_ok")
        if not copied:
            case_failed.append("wav_artifact_present")
        if play is None or play["returncode"] != 0:
            case_failed.append("audible_playback_ok")
        failed_gates.extend([f"{case_id}:{gate}" for gate in case_failed])
        results.append(
            {
                "case_id": case_id,
                "query": case["query"],
                "spoken_text": text,
                "render_receipt": str(receipt),
                "wav": str(wav) if copied else None,
                "render": render,
                "play": play,
                "failed_gates": case_failed,
            }
        )
    summary = {
        "schema": "embry.intelligence_stress.spoken_failures.v1",
        "mocked": False,
        "live": True,
        "ok": not failed_gates,
        "results": results,
        "failed_gates": failed_gates,
    }
    (out_dir / "spoken-failures.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--brave-script", default=DEFAULT_BRAVE, type=Path)
    parser.add_argument("--timeout-s", default=120, type=int)
    parser.add_argument("--render-spoken-failures", action="store_true")
    parser.add_argument("--playback-sink-target", default="64")
    parser.add_argument("--playback-timeout-s", default=60, type=int)
    parser.add_argument("--matrix-file", type=Path)
    parser.add_argument("--matrix-folder")
    parser.add_argument("--matrix-difficulty")
    parser.add_argument("--matrix-offset", default=0, type=int)
    parser.add_argument("--matrix-limit", type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix_selection: dict[str, Any] | None = None
    if args.matrix_file:
        matrix = json.loads(args.matrix_file.read_text(encoding="utf-8"))
        selected = select_matrix_sessions(
            matrix,
            folder=args.matrix_folder,
            difficulty=args.matrix_difficulty,
            offset=args.matrix_offset,
            limit=args.matrix_limit,
        )
        events_path = out_dir / "matrix-case-events.jsonl"
        cases = []
        for sequence, session in enumerate(selected, start=1):
            case = run_matrix_session(
                session,
                memory_url=args.memory_url,
                brave_script=args.brave_script,
                timeout_s=args.timeout_s,
            )
            case["sequence"] = sequence
            cases.append(case)
            append_jsonl(
                events_path,
                {
                    "type": "matrix_case_completed",
                    "sequence": sequence,
                    "id": case.get("id"),
                    "ok": case.get("ok"),
                    "live": case.get("live"),
                    "failed_gates": case.get("failed_gates", []),
                    "route": case.get("route"),
                    "ended_at_utc": utc_now(),
                },
            )
        matrix_selection = {
            "matrix_file": str(args.matrix_file),
            "folder": args.matrix_folder,
            "difficulty": args.matrix_difficulty,
            "offset": args.matrix_offset,
            "limit": args.matrix_limit,
            "selected_count": len(selected),
            "events_jsonl": str(events_path),
        }
    else:
        cases = [run_memory_case(case, memory_url=args.memory_url, timeout_s=args.timeout_s) for case in CASES]
        cases.append(run_brave_case(brave_script=args.brave_script, timeout_s=args.timeout_s))
    spoken = (
        render_spoken_failures(
            cases=cases,
            out_dir=out_dir / "spoken-failures",
            playback_sink_target=args.playback_sink_target,
            timeout_s=args.timeout_s,
            playback_timeout_s=args.playback_timeout_s,
        )
        if args.render_spoken_failures
        else {"skipped": True}
    )
    failed = [f"{case['id']}:{gate}" for case in cases for gate in case.get("failed_gates", [])]
    if args.render_spoken_failures and spoken.get("failed_gates"):
        failed.extend([f"spoken_failures:{gate}" for gate in spoken["failed_gates"]])
    receipt = {
        "schema": "embry.intelligence_stress.v1",
        "run_id": out_dir.name,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "mocked": False,
        "live": all(bool(case.get("live")) for case in cases),
        "ok": not failed,
        "cases": cases,
        "matrix_selection": matrix_selection,
        "spoken_failures": spoken,
        "failed_gates": failed,
        "claims": {
            "proves": ["memory_and_brave_routes_return_relevant_answerable_results_before_voice"]
            if not failed
            else [],
            "does_not_prove": [
                "browser_chat_ui_sync",
                "full_spoken_multiturn_conversation",
                "human_acceptance_of_voice_performance",
            ],
        },
    }
    out_path = out_dir / "receipt.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "failed_gates": failed,
                "receipt": str(out_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
