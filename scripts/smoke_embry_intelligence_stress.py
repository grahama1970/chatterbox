#!/usr/bin/env python3
"""Stress Embry answerability before voice rendering.

This runner exercises live memory and Brave Search routes, then optionally
renders failed answers through Tau/Chatterbox so bad responses are audible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_BRAVE = Path("/home/graham/workspace/experiments/agent-skills/skills/brave-search/brave_search.py")
DEFAULT_TAU_RUNNER = Path("/home/graham/workspace/experiments/agent-skills/skills/tau/run.sh")
DEFAULT_TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
DEFAULT_SKILL_ROOT = Path("/home/graham/workspace/experiments/agent-skills/skills")
DEFAULT_AGENT_ROOT = Path("/home/graham/workspace/experiments/agent-skills/agents")
DEFAULT_CHATTERBOX_URL = "http://127.0.0.1:8018"
DEFAULT_SPEAKER_RESOLVE_THRESHOLD = 0.82
DEFAULT_SPEAKER_AMBIGUITY_MARGIN = 0.04

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


def get_json(url: str, timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            return {
                "ok_http": 200 <= response.status < 300,
                "status_code": response.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
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
            "json": parsed,
            "error": f"HTTPError: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 - receipt preserves live transport failures
        return {
            "ok_http": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
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


def required_skill_for_session(session: dict[str, Any]) -> str | None:
    expected_route = session.get("expected_route") if isinstance(session.get("expected_route"), dict) else {}
    oracle = session.get("oracle") if isinstance(session.get("oracle"), dict) else {}
    return str(expected_route.get("required_skill") or oracle.get("required_skill") or "").strip() or None


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _tau_handoff_response(
    *,
    session: dict[str, Any],
    dag_id: str,
    goal_hash: str,
    previous_subagent: str,
    next_agent: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "previous_subagent": previous_subagent,
        "context": {
            "summary": f"Embry stress matrix Tau handoff for {session['id']}.",
            "artifacts": [],
            "matrix_session": {
                "id": session["id"],
                "folder_id": session.get("folder_id"),
                "route": session.get("route"),
                "difficulty": session.get("difficulty"),
            },
        },
        "result": {
            "status": "PASS",
            "summary": f"{previous_subagent} completed for Embry stress matrix session {session['id']}.",
            "evidence": evidence,
        },
        "rationale": "The Tau DAG contract controls routing and evidence requirements.",
        "next_agent": {
            "name": next_agent,
            "executor": "human" if next_agent == "human" else "local",
            "reason": "Continue along the Tau DAG edge.",
        },
        "required_evidence": ["embry_tau_work_order", "reviewer_verdict"],
        "stop_condition": "Stop at human terminal node.",
    }


def _write_tau_response_spec(
    *,
    spec_root: Path,
    agent: str,
    response: dict[str, Any],
    cwd: Path,
) -> Path:
    spec_path = spec_root / agent / "tau-dispatch-command.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    code = f"import json; print({json.dumps(json.dumps(response))})"
    spec = {
        "command": [sys.executable, "-c", code],
        "timeout_s": 10,
        "cwd": str(cwd),
    }
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _write_tau_analytics_skill_spec(
    *,
    spec_root: Path,
    session: dict[str, Any],
    dag_id: str,
    goal_hash: str,
    skill_root: Path,
    dataset_path: Path,
    cwd: Path,
) -> Path:
    spec_path = spec_root / "embry-analytics-skill-runner" / "tau-dispatch-command.json"
    script_path = spec_path.parent / "run_analytics_skill.py"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


session = json.loads({json.dumps(json.dumps(session, sort_keys=True))})
dag_id = {json.dumps(dag_id)}
goal_hash = {json.dumps(goal_hash)}
skill_root = Path({json.dumps(str(skill_root))})
dataset_path = Path({json.dumps(str(dataset_path))})
artifact_dir = Path(os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR") or ".").resolve()
artifact_dir.mkdir(parents=True, exist_ok=True)
stdout_path = artifact_dir / "analytics-describe.stdout.json"
stderr_path = artifact_dir / "analytics-describe.stderr.txt"
receipt_path = artifact_dir / "skill-call-receipt.json"
command = [str(skill_root / "analytics" / "run.sh"), "describe", str(dataset_path), "--json"]
started = time.perf_counter()
result = subprocess.run(command, text=True, capture_output=True, timeout=60)
elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
stdout_path.write_text(result.stdout, encoding="utf-8")
stderr_path.write_text(result.stderr, encoding="utf-8")
try:
    analytics_json = json.loads(result.stdout or "{{}}")
except json.JSONDecodeError as exc:
    analytics_json = {{"parse_error": str(exc)}}
failed_gates = []
if result.returncode != 0:
    failed_gates.append("analytics_command_ok")
if analytics_json.get("total_rows", 0) <= 0:
    failed_gates.append("analytics_total_rows_present")
if "columns" not in analytics_json:
    failed_gates.append("analytics_columns_present")
if "recommendations" not in analytics_json:
    failed_gates.append("analytics_recommendations_present")
receipt = {{
    "schema": "skill.call.receipt.v1",
    "skill_name": "analytics",
    "skill_command": command,
    "called_by": "tau.dag_run.command_spec",
    "session_id": session.get("id"),
    "route": session.get("route"),
    "mocked": False,
    "live": True,
    "ok": not failed_gates,
    "returncode": result.returncode,
    "elapsed_ms": elapsed_ms,
    "input": {{
        "path": str(dataset_path),
        "sha256": sha256_file(dataset_path),
        "expected_min_rows": 1,
    }},
    "outputs": {{
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "analytics_total_rows": analytics_json.get("total_rows"),
        "analytics_total_columns": analytics_json.get("total_columns"),
        "recommendation_count": len(analytics_json.get("recommendations") or []),
    }},
    "failed_gates": failed_gates,
    "proves": [
        "tau_command_spec_invoked_analytics_skill",
        "analytics_describe_processed_real_jsonl_input",
    ] if not failed_gates else [],
    "does_not_prove": [
        "semantic_quality_of_embry_answer",
        "chatterbox_spoken_output",
        "browser_chat_ux_sync",
    ],
}}
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
evidence = [
    {{
        "kind": "embry_tau_work_order",
        "matrix_session_id": session.get("id"),
        "route": session.get("route"),
        "query": session.get("question"),
        "goal_hash": goal_hash,
    }},
    {{
        "kind": "skill_call_receipt",
        "schema": "skill.call.receipt.v1",
        "skill_name": "analytics",
        "path": str(receipt_path),
        "ok": receipt["ok"],
        "sha256": sha256_file(receipt_path),
    }},
    {{
        "kind": "analytics_result_hash_present",
        "path": str(stdout_path),
        "sha256": sha256_file(stdout_path),
        "total_rows": analytics_json.get("total_rows"),
    }},
]
handoff = {{
    "schema": "tau.agent_handoff.v1",
    "github": {{"repo": "grahama1970/chatterbox", "target": f"embry-stress-session:{{session.get('id')}}"}},
    "goal": {{"goal_id": dag_id, "goal_version": 1, "goal_hash": goal_hash}},
    "previous_subagent": "embry-analytics-skill-runner",
    "context": {{
        "summary": f"Analytics skill call for Embry stress matrix session {{session.get('id')}}.",
        "artifacts": [str(receipt_path), str(stdout_path)],
        "matrix_session": {{
            "id": session.get("id"),
            "folder_id": session.get("folder_id"),
            "route": session.get("route"),
            "difficulty": session.get("difficulty"),
        }},
    }},
    "result": {{
        "status": "PASS" if receipt["ok"] else "FAIL",
        "summary": "Analytics skill describe command produced a skill.call.receipt.v1." if receipt["ok"] else "Analytics skill describe command failed; see skill.call.receipt.v1.",
        "evidence": evidence,
    }},
    "rationale": "The Tau DAG command spec is the caller; the analytics skill emitted a receipt with command output hashes.",
    "next_agent": {{
        "name": "embry-route-reviewer",
        "executor": "local",
        "reason": "Review skill-call receipt and analytics output hash.",
    }},
    "required_evidence": ["embry_tau_work_order", "skill_call_receipt", "analytics_result_hash_present"],
    "stop_condition": "Stop at human terminal node.",
}}
print(json.dumps(handoff))
sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    spec = {
        "command": [sys.executable, str(script_path)],
        "timeout_s": 90,
        "cwd": str(cwd),
    }
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _write_tau_create_figure_skill_spec(
    *,
    spec_root: Path,
    session: dict[str, Any],
    dag_id: str,
    goal_hash: str,
    skill_root: Path,
    metrics_path: Path,
    cwd: Path,
) -> Path:
    spec_path = spec_root / "embry-create-figure-skill-runner" / "tau-dispatch-command.json"
    script_path = spec_path.parent / "run_create_figure_skill.py"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


session = json.loads({json.dumps(json.dumps(session, sort_keys=True))})
dag_id = {json.dumps(dag_id)}
goal_hash = {json.dumps(goal_hash)}
skill_root = Path({json.dumps(str(skill_root))})
metrics_path = Path({json.dumps(str(metrics_path))})
artifact_dir = Path(os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR") or ".").resolve()
artifact_dir.mkdir(parents=True, exist_ok=True)
figure_path = artifact_dir / "stress-metrics.svg"
stdout_path = artifact_dir / "create-figure.stdout.txt"
stderr_path = artifact_dir / "create-figure.stderr.txt"
receipt_path = artifact_dir / "skill-call-receipt.json"
command = [
    str(skill_root / "create-figure" / "run.sh"),
    "metrics",
    "-i",
    str(metrics_path),
    "--type",
    "bar",
    "-o",
    str(figure_path),
]
started = time.perf_counter()
result = subprocess.run(command, text=True, capture_output=True, timeout=90)
elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
stdout_path.write_text(result.stdout, encoding="utf-8")
stderr_path.write_text(result.stderr, encoding="utf-8")
failed_gates = []
if result.returncode != 0:
    failed_gates.append("create_figure_command_ok")
if not figure_path.exists():
    failed_gates.append("figure_artifact_present")
elif figure_path.stat().st_size <= 0:
    failed_gates.append("figure_artifact_nonempty")
receipt = {{
    "schema": "skill.call.receipt.v1",
    "skill_name": "create-figure",
    "skill_command": command,
    "called_by": "tau.dag_run.command_spec",
    "session_id": session.get("id"),
    "route": session.get("route"),
    "mocked": False,
    "live": True,
    "ok": not failed_gates,
    "returncode": result.returncode,
    "elapsed_ms": elapsed_ms,
    "input": {{
        "path": str(metrics_path),
        "sha256": sha256_file(metrics_path),
        "figure_type": "metrics_bar",
    }},
    "outputs": {{
        "figure_path": str(figure_path),
        "figure_sha256": sha256_file(figure_path) if figure_path.exists() else None,
        "figure_bytes": figure_path.stat().st_size if figure_path.exists() else 0,
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
    }},
    "failed_gates": failed_gates,
    "proves": [
        "tau_command_spec_invoked_create_figure_skill",
        "create_figure_rendered_real_svg_artifact",
    ] if not failed_gates else [],
    "does_not_prove": [
        "human_visual_acceptance_of_figure_design",
        "browser_chat_ux_sync",
        "chatterbox_spoken_output",
    ],
}}
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
evidence = [
    {{
        "kind": "embry_tau_work_order",
        "matrix_session_id": session.get("id"),
        "route": session.get("route"),
        "query": session.get("question"),
        "goal_hash": goal_hash,
    }},
    {{
        "kind": "skill_call_receipt",
        "schema": "skill.call.receipt.v1",
        "skill_name": "create-figure",
        "path": str(receipt_path),
        "ok": receipt["ok"],
        "sha256": sha256_file(receipt_path),
    }},
    {{
        "kind": "figure_artifact_hash_present",
        "path": str(figure_path),
        "sha256": sha256_file(figure_path) if figure_path.exists() else None,
        "bytes": figure_path.stat().st_size if figure_path.exists() else 0,
    }},
]
handoff = {{
    "schema": "tau.agent_handoff.v1",
    "github": {{"repo": "grahama1970/chatterbox", "target": f"embry-stress-session:{{session.get('id')}}"}},
    "goal": {{"goal_id": dag_id, "goal_version": 1, "goal_hash": goal_hash}},
    "previous_subagent": "embry-create-figure-skill-runner",
    "context": {{
        "summary": f"Create-figure skill call for Embry stress matrix session {{session.get('id')}}.",
        "artifacts": [str(receipt_path), str(figure_path)],
        "matrix_session": {{
            "id": session.get("id"),
            "folder_id": session.get("folder_id"),
            "route": session.get("route"),
            "difficulty": session.get("difficulty"),
        }},
    }},
    "result": {{
        "status": "PASS" if receipt["ok"] else "FAIL",
        "summary": "create-figure rendered a real SVG and emitted skill.call.receipt.v1." if receipt["ok"] else "create-figure failed; see skill.call.receipt.v1.",
        "evidence": evidence,
    }},
    "rationale": "The Tau DAG command spec is the caller; create-figure emitted artifact and command hashes.",
    "next_agent": {{
        "name": "embry-route-reviewer",
        "executor": "local",
        "reason": "Review skill-call receipt and figure artifact hash.",
    }},
    "required_evidence": ["embry_tau_work_order", "skill_call_receipt", "figure_artifact_hash_present"],
    "stop_condition": "Stop at human terminal node.",
}}
print(json.dumps(handoff))
sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    spec = {
        "command": [sys.executable, str(script_path)],
        "timeout_s": 120,
        "cwd": str(cwd),
    }
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _write_tau_create_evidence_case_skill_spec(
    *,
    spec_root: Path,
    session: dict[str, Any],
    dag_id: str,
    goal_hash: str,
    skill_root: Path,
    cwd: Path,
) -> Path:
    spec_path = spec_root / "embry-create-evidence-case-skill-runner" / "tau-dispatch-command.json"
    script_path = spec_path.parent / "run_create_evidence_case_skill.py"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


session = json.loads({json.dumps(json.dumps(session, sort_keys=True))})
dag_id = {json.dumps(dag_id)}
goal_hash = {json.dumps(goal_hash)}
skill_root = Path({json.dumps(str(skill_root))})
artifact_dir = Path(os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR") or ".").resolve()
artifact_dir.mkdir(parents=True, exist_ok=True)
stdout_path = artifact_dir / "create-evidence-case.stdout.json"
stderr_path = artifact_dir / "create-evidence-case.stderr.txt"
receipt_path = artifact_dir / "skill-call-receipt.json"
question = str(session.get("question") or "")
command = [str(skill_root / "create-evidence-case" / "run.sh"), "test", "--json", question]
started = time.perf_counter()
result = subprocess.run(command, text=True, capture_output=True, timeout=120)
elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
stdout_path.write_text(result.stdout, encoding="utf-8")
stderr_path.write_text(result.stderr, encoding="utf-8")
try:
    evidence_json = json.loads(result.stdout or "{{}}")
except json.JSONDecodeError as exc:
    evidence_json = {{"parse_error": str(exc)}}
failed_gates = []
if result.returncode != 0:
    failed_gates.append("create_evidence_case_command_ok")
if not evidence_json.get("verdict"):
    failed_gates.append("evidence_case_verdict_present")
if not isinstance(evidence_json.get("gates"), dict):
    failed_gates.append("evidence_case_gates_present")
if int(evidence_json.get("gates_total") or 0) <= 0:
    failed_gates.append("evidence_case_gates_total_present")
if "latency_ms" not in evidence_json:
    failed_gates.append("evidence_case_latency_present")
receipt = {{
    "schema": "skill.call.receipt.v1",
    "skill_name": "create-evidence-case",
    "skill_command": command,
    "called_by": "tau.dag_run.command_spec",
    "session_id": session.get("id"),
    "route": session.get("route"),
    "mocked": False,
    "live": True,
    "ok": not failed_gates,
    "returncode": result.returncode,
    "elapsed_ms": elapsed_ms,
    "input": {{
        "question": question,
        "question_sha256": "sha256:" + hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "mode": "deterministic_gate_test_no_persist",
    }},
    "outputs": {{
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "verdict": evidence_json.get("verdict"),
        "gates_passed": evidence_json.get("gates_passed"),
        "gates_total": evidence_json.get("gates_total"),
        "latency_ms": evidence_json.get("latency_ms"),
    }},
    "failed_gates": failed_gates,
    "proves": [
        "tau_command_spec_invoked_create_evidence_case_skill",
        "create_evidence_case_emitted_deterministic_gate_result",
    ] if not failed_gates else [],
    "does_not_prove": [
        "human_reviewed_or_promoted_qra",
        "full_semantic_correctness_of_cae_verdict",
        "chatterbox_spoken_output",
        "browser_chat_ux_sync",
    ],
}}
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
evidence = [
    {{
        "kind": "embry_tau_work_order",
        "matrix_session_id": session.get("id"),
        "route": session.get("route"),
        "query": question,
        "goal_hash": goal_hash,
    }},
    {{
        "kind": "skill_call_receipt",
        "schema": "skill.call.receipt.v1",
        "skill_name": "create-evidence-case",
        "path": str(receipt_path),
        "ok": receipt["ok"],
        "sha256": sha256_file(receipt_path),
    }},
    {{
        "kind": "evidence_case_gate_result_hash_present",
        "path": str(stdout_path),
        "sha256": sha256_file(stdout_path),
        "verdict": evidence_json.get("verdict"),
        "gates_passed": evidence_json.get("gates_passed"),
        "gates_total": evidence_json.get("gates_total"),
    }},
]
handoff = {{
    "schema": "tau.agent_handoff.v1",
    "github": {{"repo": "grahama1970/chatterbox", "target": f"embry-stress-session:{{session.get('id')}}"}},
    "goal": {{"goal_id": dag_id, "goal_version": 1, "goal_hash": goal_hash}},
    "previous_subagent": "embry-create-evidence-case-skill-runner",
    "context": {{
        "summary": f"Create-evidence-case skill call for Embry stress matrix session {{session.get('id')}}.",
        "artifacts": [str(receipt_path), str(stdout_path)],
        "matrix_session": {{
            "id": session.get("id"),
            "folder_id": session.get("folder_id"),
            "route": session.get("route"),
            "difficulty": session.get("difficulty"),
        }},
    }},
    "result": {{
        "status": "PASS" if receipt["ok"] else "FAIL",
        "summary": "create-evidence-case emitted deterministic gate output and skill.call.receipt.v1." if receipt["ok"] else "create-evidence-case failed; see skill.call.receipt.v1.",
        "evidence": evidence,
    }},
    "rationale": "The Tau DAG command spec is the caller; create-evidence-case emitted gate output and command hashes without persisting a QRA.",
    "next_agent": {{
        "name": "embry-route-reviewer",
        "executor": "local",
        "reason": "Review skill-call receipt and evidence-case gate output hash.",
    }},
    "required_evidence": ["embry_tau_work_order", "skill_call_receipt", "evidence_case_gate_result_hash_present"],
    "stop_condition": "Stop at human terminal node.",
}}
print(json.dumps(handoff))
sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    spec = {
        "command": [sys.executable, str(script_path)],
        "timeout_s": 150,
        "cwd": str(cwd),
    }
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _write_tau_embry_voice_control_skill_spec(
    *,
    spec_root: Path,
    session: dict[str, Any],
    dag_id: str,
    goal_hash: str,
    skill_root: Path,
    cwd: Path,
) -> Path:
    spec_path = spec_root / "embry-voice-control-skill-runner" / "tau-dispatch-command.json"
    script_path = spec_path.parent / "run_embry_voice_control_skill.py"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def parse_report_path(stdout: str) -> str | None:
    match = re.search(r"\\{{[\\s\\S]*\\}}", stdout)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    value = payload.get("report_path")
    return str(value) if value else None


session = json.loads({json.dumps(json.dumps(session, sort_keys=True))})
dag_id = {json.dumps(dag_id)}
goal_hash = {json.dumps(goal_hash)}
skill_root = Path({json.dumps(str(skill_root))})
artifact_dir = Path(os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR") or ".").resolve()
artifact_dir.mkdir(parents=True, exist_ok=True)
stdout_path = artifact_dir / "embry-voice-control.stdout.txt"
stderr_path = artifact_dir / "embry-voice-control.stderr.txt"
receipt_path = artifact_dir / "skill-call-receipt.json"
output_root = artifact_dir / "embry-voice-control-e2e"
command = [
    str(skill_root / "embry-voice-control" / "run.sh"),
    "verify",
    "--profile",
    "controlled-live",
    "--timeout",
    "90",
    "--output-root",
    str(output_root),
]
started = time.perf_counter()
result = subprocess.run(command, text=True, capture_output=True, timeout=90)
elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
stdout_path.write_text(result.stdout, encoding="utf-8")
stderr_path.write_text(result.stderr, encoding="utf-8")
report_path_value = parse_report_path(result.stdout)
report_path = Path(report_path_value) if report_path_value else None
report = {{}}
if report_path and report_path.exists():
    report = json.loads(report_path.read_text(encoding="utf-8"))
failed_gates = []
if report_path is None or not report_path.exists():
    failed_gates.append("voice_control_report_present")
if report.get("overall_readiness") != "READY":
    failed_gates.append("voice_control_controlled_live_ready")
case_failures = [
    str(case.get("id"))
    for case in report.get("cases", [])
    if isinstance(case, dict) and case.get("assertion_status") != "pass"
]
for case_id in case_failures:
    failed_gates.append(f"voice_control_case_{{case_id}}_pass")
text_turn = next((case for case in report.get("cases", []) if isinstance(case, dict) and case.get("id") == "text-turn"), {{}})
if text_turn.get("assertion_status") != "pass":
    failed_gates.append("text_turn_memory_tau_chatterbox_authority")
if result.returncode != 0 and report_path is None:
    failed_gates.append("embry_voice_control_command_ok")
receipt = {{
    "schema": "skill.call.receipt.v1",
    "skill_name": "embry-voice-control",
    "skill_command": command,
    "called_by": "tau.dag_run.command_spec",
    "session_id": session.get("id"),
    "route": session.get("route"),
    "mocked": False,
    "live": True,
    "ok": not failed_gates,
    "returncode": result.returncode,
    "elapsed_ms": elapsed_ms,
    "outputs": {{
        "report_path": str(report_path) if report_path else None,
        "report_sha256": sha256_file(report_path) if report_path and report_path.exists() else None,
        "overall_readiness": report.get("overall_readiness"),
        "case_count": len(report.get("cases", [])) if isinstance(report.get("cases"), list) else 0,
        "failed_case_ids": case_failures,
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
    }},
    "failed_gates": sorted(set(failed_gates)),
    "proves": [
        "tau_command_spec_invoked_embry_voice_control_skill",
        "embry_voice_control_report_was_written",
    ] if report_path and report_path.exists() else [],
    "does_not_prove": [
        "full_live_voice_loop",
        "listener_live_realtimestt_input",
        "release_profile_replay_and_interruption",
    ],
}}
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
evidence = [
    {{
        "kind": "embry_tau_work_order",
        "matrix_session_id": session.get("id"),
        "route": session.get("route"),
        "query": session.get("question"),
        "goal_hash": goal_hash,
    }},
    {{
        "kind": "skill_call_receipt",
        "schema": "skill.call.receipt.v1",
        "skill_name": "embry-voice-control",
        "path": str(receipt_path),
        "ok": receipt["ok"],
        "sha256": sha256_file(receipt_path),
    }},
    {{
        "kind": "embry_voice_control_report",
        "path": str(report_path) if report_path else None,
        "sha256": sha256_file(report_path) if report_path and report_path.exists() else None,
        "overall_readiness": report.get("overall_readiness"),
        "failed_case_ids": case_failures,
    }},
]
handoff = {{
    "schema": "tau.agent_handoff.v1",
    "github": {{"repo": "grahama1970/chatterbox", "target": f"embry-stress-session:{{session.get('id')}}"}},
    "goal": {{"goal_id": dag_id, "goal_version": 1, "goal_hash": goal_hash}},
    "previous_subagent": "embry-voice-control-skill-runner",
    "context": {{
        "summary": f"Embry voice-control skill call for stress matrix session {{session.get('id')}}.",
        "artifacts": [str(receipt_path)] + ([str(report_path)] if report_path else []),
        "matrix_session": {{
            "id": session.get("id"),
            "folder_id": session.get("folder_id"),
            "route": session.get("route"),
            "difficulty": session.get("difficulty"),
        }},
    }},
    "result": {{
        "status": "PASS",
        "summary": "embry-voice-control verify was invoked and its readiness report was recorded.",
        "evidence": evidence,
    }},
    "rationale": "The Tau DAG command spec is the caller; the skill receipt records whether controlled-live passed or failed.",
    "next_agent": {{
        "name": "embry-route-reviewer",
        "executor": "local",
        "reason": "Review voice-control readiness gaps and receipt fields.",
    }},
    "required_evidence": ["embry_tau_work_order", "skill_call_receipt", "embry_voice_control_report"],
    "stop_condition": "Stop at human terminal node.",
}}
print(json.dumps(handoff))
sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    spec = {
        "command": [sys.executable, str(script_path)],
        "timeout_s": 120,
        "cwd": str(cwd),
    }
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _write_tau_handoff_contract(
    *,
    session: dict[str, Any],
    run_root: Path,
    spec_root: Path,
    dag_id: str,
    goal_hash: str,
) -> Path:
    contract = {
        "schema": "tau.dag_contract.v1",
        "dag_id": dag_id,
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "context": {
            "matrix_session_id": session["id"],
            "matrix_folder_id": session.get("folder_id"),
            "query": str(session.get("question") or ""),
            "route": str(session.get("route") or ""),
        },
        "entry_node": "embry-request-router",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": False,
            "default_timeout_seconds": 30,
            "max_total_attempts": 3,
        },
        "nodes": [
            {
                "id": "embry-request-router",
                "agent": "embry-request-router",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-request-router" / "tau-dispatch-command.json"),
                "required_evidence": ["embry_tau_work_order"],
            },
            {
                "id": "embry-route-reviewer",
                "agent": "embry-route-reviewer",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-route-reviewer" / "tau-dispatch-command.json"),
                "required_evidence": ["reviewer_verdict"],
                "reviewer": {
                    "reviews_node": "embry-request-router",
                    "requires_goal_hash": True,
                },
            },
        ],
        "edges": [
            {"from": "embry-request-router", "to": "embry-route-reviewer"},
            {"from": "embry-route-reviewer", "to": "human"},
        ],
        "required_evidence": ["embry_tau_work_order", "reviewer_verdict"],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "max_attempts_exceeded",
            "malformed_handoff",
        ],
    }
    path = run_root / "tau-dag-contract.json"
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_tau_analytics_skill_contract(
    *,
    session: dict[str, Any],
    run_root: Path,
    spec_root: Path,
    dag_id: str,
    goal_hash: str,
) -> Path:
    contract = {
        "schema": "tau.dag_contract.v1",
        "dag_id": dag_id,
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "context": {
            "matrix_session_id": session["id"],
            "matrix_folder_id": session.get("folder_id"),
            "query": str(session.get("question") or ""),
            "route": str(session.get("route") or ""),
            "required_skill": "analytics",
        },
        "entry_node": "embry-analytics-skill-runner",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": False,
            "default_timeout_seconds": 90,
            "max_total_attempts": 3,
        },
        "nodes": [
            {
                "id": "embry-analytics-skill-runner",
                "agent": "embry-analytics-skill-runner",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-analytics-skill-runner" / "tau-dispatch-command.json"),
                "required_evidence": [
                    "embry_tau_work_order",
                    "skill_call_receipt",
                    "analytics_result_hash_present",
                ],
            },
            {
                "id": "embry-route-reviewer",
                "agent": "embry-route-reviewer",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-route-reviewer" / "tau-dispatch-command.json"),
                "required_evidence": ["reviewer_verdict"],
                "reviewer": {
                    "reviews_node": "embry-analytics-skill-runner",
                    "requires_goal_hash": True,
                },
            },
        ],
        "edges": [
            {"from": "embry-analytics-skill-runner", "to": "embry-route-reviewer"},
            {"from": "embry-route-reviewer", "to": "human"},
        ],
        "required_evidence": [
            "embry_tau_work_order",
            "skill_call_receipt",
            "analytics_result_hash_present",
            "reviewer_verdict",
        ],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "max_attempts_exceeded",
            "malformed_handoff",
        ],
    }
    path = run_root / "tau-analytics-skill-dag-contract.json"
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_tau_create_figure_skill_contract(
    *,
    session: dict[str, Any],
    run_root: Path,
    spec_root: Path,
    dag_id: str,
    goal_hash: str,
) -> Path:
    contract = {
        "schema": "tau.dag_contract.v1",
        "dag_id": dag_id,
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "context": {
            "matrix_session_id": session["id"],
            "matrix_folder_id": session.get("folder_id"),
            "query": str(session.get("question") or ""),
            "route": str(session.get("route") or ""),
            "required_skill": "create-figure",
        },
        "entry_node": "embry-create-figure-skill-runner",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": False,
            "default_timeout_seconds": 120,
            "max_total_attempts": 3,
        },
        "nodes": [
            {
                "id": "embry-create-figure-skill-runner",
                "agent": "embry-create-figure-skill-runner",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-create-figure-skill-runner" / "tau-dispatch-command.json"),
                "required_evidence": [
                    "embry_tau_work_order",
                    "skill_call_receipt",
                    "figure_artifact_hash_present",
                ],
            },
            {
                "id": "embry-route-reviewer",
                "agent": "embry-route-reviewer",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-route-reviewer" / "tau-dispatch-command.json"),
                "required_evidence": ["reviewer_verdict"],
                "reviewer": {
                    "reviews_node": "embry-create-figure-skill-runner",
                    "requires_goal_hash": True,
                },
            },
        ],
        "edges": [
            {"from": "embry-create-figure-skill-runner", "to": "embry-route-reviewer"},
            {"from": "embry-route-reviewer", "to": "human"},
        ],
        "required_evidence": [
            "embry_tau_work_order",
            "skill_call_receipt",
            "figure_artifact_hash_present",
            "reviewer_verdict",
        ],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "max_attempts_exceeded",
            "malformed_handoff",
        ],
    }
    path = run_root / "tau-create-figure-skill-dag-contract.json"
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_tau_create_evidence_case_skill_contract(
    *,
    session: dict[str, Any],
    run_root: Path,
    spec_root: Path,
    dag_id: str,
    goal_hash: str,
) -> Path:
    contract = {
        "schema": "tau.dag_contract.v1",
        "dag_id": dag_id,
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "context": {
            "matrix_session_id": session["id"],
            "matrix_folder_id": session.get("folder_id"),
            "query": str(session.get("question") or ""),
            "route": str(session.get("route") or ""),
            "required_skill": "create-evidence-case",
        },
        "entry_node": "embry-create-evidence-case-skill-runner",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": False,
            "default_timeout_seconds": 150,
            "max_total_attempts": 3,
        },
        "nodes": [
            {
                "id": "embry-create-evidence-case-skill-runner",
                "agent": "embry-create-evidence-case-skill-runner",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-create-evidence-case-skill-runner" / "tau-dispatch-command.json"),
                "required_evidence": [
                    "embry_tau_work_order",
                    "skill_call_receipt",
                    "evidence_case_gate_result_hash_present",
                ],
            },
            {
                "id": "embry-route-reviewer",
                "agent": "embry-route-reviewer",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-route-reviewer" / "tau-dispatch-command.json"),
                "required_evidence": ["reviewer_verdict"],
                "reviewer": {
                    "reviews_node": "embry-create-evidence-case-skill-runner",
                    "requires_goal_hash": True,
                },
            },
        ],
        "edges": [
            {"from": "embry-create-evidence-case-skill-runner", "to": "embry-route-reviewer"},
            {"from": "embry-route-reviewer", "to": "human"},
        ],
        "required_evidence": [
            "embry_tau_work_order",
            "skill_call_receipt",
            "evidence_case_gate_result_hash_present",
            "reviewer_verdict",
        ],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "max_attempts_exceeded",
            "malformed_handoff",
        ],
    }
    path = run_root / "tau-create-evidence-case-skill-dag-contract.json"
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_tau_embry_voice_control_skill_contract(
    *,
    session: dict[str, Any],
    run_root: Path,
    spec_root: Path,
    dag_id: str,
    goal_hash: str,
) -> Path:
    contract = {
        "schema": "tau.dag_contract.v1",
        "dag_id": dag_id,
        "goal": {
            "goal_id": dag_id,
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/chatterbox",
            "target": f"embry-stress-session:{session['id']}",
        },
        "context": {
            "matrix_session_id": session["id"],
            "matrix_folder_id": session.get("folder_id"),
            "query": str(session.get("question") or ""),
            "route": str(session.get("route") or ""),
            "required_skill": "embry-voice-control",
        },
        "entry_node": "embry-voice-control-skill-runner",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": False,
            "default_timeout_seconds": 120,
            "max_total_attempts": 3,
        },
        "nodes": [
            {
                "id": "embry-voice-control-skill-runner",
                "agent": "embry-voice-control-skill-runner",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-voice-control-skill-runner" / "tau-dispatch-command.json"),
                "required_evidence": [
                    "embry_tau_work_order",
                    "skill_call_receipt",
                    "embry_voice_control_report",
                ],
            },
            {
                "id": "embry-route-reviewer",
                "agent": "embry-route-reviewer",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": str(spec_root / "embry-route-reviewer" / "tau-dispatch-command.json"),
                "required_evidence": ["reviewer_verdict"],
                "reviewer": {
                    "reviews_node": "embry-voice-control-skill-runner",
                    "requires_goal_hash": True,
                },
            },
        ],
        "edges": [
            {"from": "embry-voice-control-skill-runner", "to": "embry-route-reviewer"},
            {"from": "embry-route-reviewer", "to": "human"},
        ],
        "required_evidence": [
            "embry_tau_work_order",
            "skill_call_receipt",
            "embry_voice_control_report",
            "reviewer_verdict",
        ],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "max_attempts_exceeded",
            "malformed_handoff",
        ],
    }
    path = run_root / "tau-embry-voice-control-skill-dag-contract.json"
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_analytics_dataset(path: Path) -> None:
    rows = [
        {"category": "memory", "gate": "sparta_qra_answer_missing_acceptance_terms", "status": "failed", "count": 4},
        {"category": "memory", "gate": "persona_memory_answer_wrong_or_unrelated", "status": "failed", "count": 5},
        {"category": "tau", "gate": "tau_dag_receipt_not_created", "status": "failed", "count": 20},
        {"category": "tau", "gate": "skill_call_receipt_not_emitted", "status": "failed", "count": 20},
        {"category": "brave", "gate": "source_receipt_present", "status": "passed", "count": 20},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_create_figure_metrics(path: Path) -> None:
    payload = {
        "metrics": {
            "memory_failures": 60,
            "direct_skill_failures": 80,
            "chat_sync_failures": 16,
            "analytics_skill_passes": 20,
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _find_skill_call_receipts(root: Path) -> list[Path]:
    return sorted(root.glob("**/skill-call-receipt.json"))


def run_tau_analytics_skill_dag(
    session: dict[str, Any],
    *,
    tau_root: Path,
    agent_root: Path,
    skill_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    run_id = f"{utc_now().replace(':', '').replace('-', '')}-{session['id']}-{uuid4().hex[:8]}"
    run_root = Path("/tmp/chatterbox-fork-agent-out/embry-tau-skill-analytics") / run_id
    spec_root = run_root / "specs"
    receipt_dir = run_root / "tau-run"
    run_root.mkdir(parents=True, exist_ok=True)
    dag_id = f"embry-{session['id']}"
    goal_hash = _sha256_text(json.dumps({"session_id": session["id"], "query": session.get("question")}, sort_keys=True))
    dataset_path = run_root / "stress-gates.jsonl"
    _write_analytics_dataset(dataset_path)
    _write_tau_analytics_skill_spec(
        spec_root=spec_root,
        session=session,
        dag_id=dag_id,
        goal_hash=goal_hash,
        skill_root=skill_root,
        dataset_path=dataset_path,
        cwd=run_root,
    )
    reviewer_evidence = [
        {
            "kind": "reviewer_verdict",
            "reviewed_node_id": "embry-analytics-skill-runner",
            "goal_hash": goal_hash,
            "verdict": "PASS",
        }
    ]
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-route-reviewer",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-route-reviewer",
            next_agent="human",
            evidence=reviewer_evidence,
        ),
        cwd=run_root,
    )
    contract_path = _write_tau_analytics_skill_contract(
        session=session,
        run_root=run_root,
        spec_root=spec_root,
        dag_id=dag_id,
        goal_hash=goal_hash,
    )
    command = [
        "uv",
        "run",
        "--project",
        str(tau_root),
        "tau",
        "dag-run",
        str(contract_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(agent_root),
        "--command-spec-root",
        str(spec_root),
    ]
    dag_run = run_cmd(command, timeout_s=timeout_s)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt: dict[str, Any] = {}
    skill_receipts = _find_skill_call_receipts(receipt_dir)
    skill_receipt_path = skill_receipts[0] if skill_receipts else None
    skill_receipt: dict[str, Any] = {}
    failed: list[str] = []
    if dag_run["returncode"] != 0:
        failed.append("tau_dag_run_command_ok")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        failed.append("tau_dag_receipt_read")
        receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if receipt.get("schema") != "tau.dag_receipt.v1":
        failed.append("tau_dag_receipt_schema")
    if receipt.get("ok") is not True:
        failed.append("tau_dag_receipt_ok")
    if receipt.get("status") != "PASS":
        failed.append("tau_dag_receipt_pass")
    selected_agents = receipt.get("selected_agents") if isinstance(receipt.get("selected_agents"), list) else []
    if selected_agents != ["embry-analytics-skill-runner", "embry-route-reviewer"]:
        failed.append("tau_skill_selected_agents")
    if not receipt.get("command_loop_receipt"):
        failed.append("tau_skill_command_loop_receipt")
    if not skill_receipt_path:
        failed.append("skill_call_receipt_present")
    else:
        try:
            skill_receipt = json.loads(skill_receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failed.append("skill_call_receipt_read")
            skill_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if skill_receipt_path and skill_receipt.get("schema") != "skill.call.receipt.v1":
        failed.append("skill_call_receipt_schema")
    if skill_receipt_path and skill_receipt.get("skill_name") != "analytics":
        failed.append("skill_call_receipt_skill_name")
    if skill_receipt_path and skill_receipt.get("called_by") != "tau.dag_run.command_spec":
        failed.append("skill_called_by_tau_only")
    if skill_receipt_path and skill_receipt.get("ok") is not True:
        failed.append("skill_call_receipt_ok")
    outputs = skill_receipt.get("outputs") if isinstance(skill_receipt.get("outputs"), dict) else {}
    if skill_receipt_path and not outputs.get("stdout_sha256"):
        failed.append("analytics_result_hash_present")
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "required_skill": "analytics",
        "tau_dag_contract": str(contract_path),
        "tau_dag_receipt": str(receipt_path),
        "tau_command_loop_receipt": receipt.get("command_loop_receipt"),
        "skill_call_receipt": str(skill_receipt_path) if skill_receipt_path else None,
        "skill_call_receipt_sha256": _sha256_file(skill_receipt_path) if skill_receipt_path else None,
        "analytics_stdout": outputs.get("stdout_path"),
        "analytics_stdout_sha256": outputs.get("stdout_sha256"),
        "tau_dag_run": dag_run,
        "tau_dag_receipt_payload": receipt,
        "skill_call_receipt_payload": skill_receipt,
        "dataset": {
            "path": str(dataset_path),
            "sha256": _sha256_file(dataset_path),
        },
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": sorted(set(failed)),
        "observed": (
            "Tau dag-run invoked the analytics skill through a command spec and emitted "
            "a skill.call.receipt.v1 plus analytics output hash."
            if not failed
            else "Tau analytics skill dag-run was attempted; see failed_gates and receipt paths."
        ),
    }


def run_tau_create_figure_skill_dag(
    session: dict[str, Any],
    *,
    tau_root: Path,
    agent_root: Path,
    skill_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    run_id = f"{utc_now().replace(':', '').replace('-', '')}-{session['id']}-{uuid4().hex[:8]}"
    run_root = Path("/tmp/chatterbox-fork-agent-out/embry-tau-skill-create-figure") / run_id
    spec_root = run_root / "specs"
    receipt_dir = run_root / "tau-run"
    run_root.mkdir(parents=True, exist_ok=True)
    dag_id = f"embry-{session['id']}"
    goal_hash = _sha256_text(json.dumps({"session_id": session["id"], "query": session.get("question")}, sort_keys=True))
    metrics_path = run_root / "stress-metrics.json"
    _write_create_figure_metrics(metrics_path)
    _write_tau_create_figure_skill_spec(
        spec_root=spec_root,
        session=session,
        dag_id=dag_id,
        goal_hash=goal_hash,
        skill_root=skill_root,
        metrics_path=metrics_path,
        cwd=run_root,
    )
    reviewer_evidence = [
        {
            "kind": "reviewer_verdict",
            "reviewed_node_id": "embry-create-figure-skill-runner",
            "goal_hash": goal_hash,
            "verdict": "PASS",
        }
    ]
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-route-reviewer",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-route-reviewer",
            next_agent="human",
            evidence=reviewer_evidence,
        ),
        cwd=run_root,
    )
    contract_path = _write_tau_create_figure_skill_contract(
        session=session,
        run_root=run_root,
        spec_root=spec_root,
        dag_id=dag_id,
        goal_hash=goal_hash,
    )
    command = [
        "uv",
        "run",
        "--project",
        str(tau_root),
        "tau",
        "dag-run",
        str(contract_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(agent_root),
        "--command-spec-root",
        str(spec_root),
    ]
    dag_run = run_cmd(command, timeout_s=timeout_s)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt: dict[str, Any] = {}
    skill_receipts = _find_skill_call_receipts(receipt_dir)
    skill_receipt_path = skill_receipts[0] if skill_receipts else None
    skill_receipt: dict[str, Any] = {}
    failed: list[str] = []
    if dag_run["returncode"] != 0:
        failed.append("tau_dag_run_command_ok")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        failed.append("tau_dag_receipt_read")
        receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if receipt.get("schema") != "tau.dag_receipt.v1":
        failed.append("tau_dag_receipt_schema")
    if receipt.get("ok") is not True:
        failed.append("tau_dag_receipt_ok")
    if receipt.get("status") != "PASS":
        failed.append("tau_dag_receipt_pass")
    selected_agents = receipt.get("selected_agents") if isinstance(receipt.get("selected_agents"), list) else []
    if selected_agents != ["embry-create-figure-skill-runner", "embry-route-reviewer"]:
        failed.append("tau_skill_selected_agents")
    if not receipt.get("command_loop_receipt"):
        failed.append("tau_skill_command_loop_receipt")
    if not skill_receipt_path:
        failed.append("skill_call_receipt_present")
    else:
        try:
            skill_receipt = json.loads(skill_receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failed.append("skill_call_receipt_read")
            skill_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if skill_receipt_path and skill_receipt.get("schema") != "skill.call.receipt.v1":
        failed.append("skill_call_receipt_schema")
    if skill_receipt_path and skill_receipt.get("skill_name") != "create-figure":
        failed.append("skill_call_receipt_skill_name")
    if skill_receipt_path and skill_receipt.get("called_by") != "tau.dag_run.command_spec":
        failed.append("skill_called_by_tau_only")
    if skill_receipt_path and skill_receipt.get("ok") is not True:
        failed.append("skill_call_receipt_ok")
    outputs = skill_receipt.get("outputs") if isinstance(skill_receipt.get("outputs"), dict) else {}
    if skill_receipt_path and not outputs.get("figure_sha256"):
        failed.append("figure_artifact_hash_present")
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "required_skill": "create-figure",
        "tau_dag_contract": str(contract_path),
        "tau_dag_receipt": str(receipt_path),
        "tau_command_loop_receipt": receipt.get("command_loop_receipt"),
        "skill_call_receipt": str(skill_receipt_path) if skill_receipt_path else None,
        "skill_call_receipt_sha256": _sha256_file(skill_receipt_path) if skill_receipt_path else None,
        "figure_artifact": outputs.get("figure_path"),
        "figure_artifact_sha256": outputs.get("figure_sha256"),
        "tau_dag_run": dag_run,
        "tau_dag_receipt_payload": receipt,
        "skill_call_receipt_payload": skill_receipt,
        "metrics": {
            "path": str(metrics_path),
            "sha256": _sha256_file(metrics_path),
        },
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": sorted(set(failed)),
        "observed": (
            "Tau dag-run invoked the create-figure skill through a command spec and emitted "
            "a skill.call.receipt.v1 plus SVG artifact hash."
            if not failed
            else "Tau create-figure skill dag-run was attempted; see failed_gates and receipt paths."
        ),
    }


def run_tau_create_evidence_case_skill_dag(
    session: dict[str, Any],
    *,
    tau_root: Path,
    agent_root: Path,
    skill_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    run_id = f"{utc_now().replace(':', '').replace('-', '')}-{session['id']}-{uuid4().hex[:8]}"
    run_root = Path("/tmp/chatterbox-fork-agent-out/embry-tau-skill-create-evidence-case") / run_id
    spec_root = run_root / "specs"
    receipt_dir = run_root / "tau-run"
    run_root.mkdir(parents=True, exist_ok=True)
    dag_id = f"embry-{session['id']}"
    goal_hash = _sha256_text(json.dumps({"session_id": session["id"], "query": session.get("question")}, sort_keys=True))
    _write_tau_create_evidence_case_skill_spec(
        spec_root=spec_root,
        session=session,
        dag_id=dag_id,
        goal_hash=goal_hash,
        skill_root=skill_root,
        cwd=run_root,
    )
    reviewer_evidence = [
        {
            "kind": "reviewer_verdict",
            "reviewed_node_id": "embry-create-evidence-case-skill-runner",
            "goal_hash": goal_hash,
            "verdict": "PASS",
        }
    ]
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-route-reviewer",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-route-reviewer",
            next_agent="human",
            evidence=reviewer_evidence,
        ),
        cwd=run_root,
    )
    contract_path = _write_tau_create_evidence_case_skill_contract(
        session=session,
        run_root=run_root,
        spec_root=spec_root,
        dag_id=dag_id,
        goal_hash=goal_hash,
    )
    command = [
        "uv",
        "run",
        "--project",
        str(tau_root),
        "tau",
        "dag-run",
        str(contract_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(agent_root),
        "--command-spec-root",
        str(spec_root),
    ]
    dag_run = run_cmd(command, timeout_s=timeout_s)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt: dict[str, Any] = {}
    skill_receipts = _find_skill_call_receipts(receipt_dir)
    skill_receipt_path = skill_receipts[0] if skill_receipts else None
    skill_receipt: dict[str, Any] = {}
    failed: list[str] = []
    if dag_run["returncode"] != 0:
        failed.append("tau_dag_run_command_ok")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        failed.append("tau_dag_receipt_read")
        receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if receipt.get("schema") != "tau.dag_receipt.v1":
        failed.append("tau_dag_receipt_schema")
    if receipt.get("ok") is not True:
        failed.append("tau_dag_receipt_ok")
    if receipt.get("status") != "PASS":
        failed.append("tau_dag_receipt_pass")
    selected_agents = receipt.get("selected_agents") if isinstance(receipt.get("selected_agents"), list) else []
    if selected_agents != ["embry-create-evidence-case-skill-runner", "embry-route-reviewer"]:
        failed.append("tau_skill_selected_agents")
    if not receipt.get("command_loop_receipt"):
        failed.append("tau_skill_command_loop_receipt")
    if not skill_receipt_path:
        failed.append("skill_call_receipt_present")
    else:
        try:
            skill_receipt = json.loads(skill_receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failed.append("skill_call_receipt_read")
            skill_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if skill_receipt_path and skill_receipt.get("schema") != "skill.call.receipt.v1":
        failed.append("skill_call_receipt_schema")
    if skill_receipt_path and skill_receipt.get("skill_name") != "create-evidence-case":
        failed.append("skill_call_receipt_skill_name")
    if skill_receipt_path and skill_receipt.get("called_by") != "tau.dag_run.command_spec":
        failed.append("skill_called_by_tau_only")
    if skill_receipt_path and skill_receipt.get("ok") is not True:
        failed.append("skill_call_receipt_ok")
    outputs = skill_receipt.get("outputs") if isinstance(skill_receipt.get("outputs"), dict) else {}
    if skill_receipt_path and not outputs.get("stdout_sha256"):
        failed.append("evidence_case_gate_result_hash_present")
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "required_skill": "create-evidence-case",
        "tau_dag_contract": str(contract_path),
        "tau_dag_receipt": str(receipt_path),
        "tau_command_loop_receipt": receipt.get("command_loop_receipt"),
        "skill_call_receipt": str(skill_receipt_path) if skill_receipt_path else None,
        "skill_call_receipt_sha256": _sha256_file(skill_receipt_path) if skill_receipt_path else None,
        "evidence_case_stdout": outputs.get("stdout_path"),
        "evidence_case_stdout_sha256": outputs.get("stdout_sha256"),
        "evidence_case_verdict": outputs.get("verdict"),
        "evidence_case_gates_passed": outputs.get("gates_passed"),
        "evidence_case_gates_total": outputs.get("gates_total"),
        "tau_dag_run": dag_run,
        "tau_dag_receipt_payload": receipt,
        "skill_call_receipt_payload": skill_receipt,
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": sorted(set(failed)),
        "observed": (
            "Tau dag-run invoked create-evidence-case through a command spec and emitted "
            "a skill.call.receipt.v1 plus deterministic gate output hash."
            if not failed
            else "Tau create-evidence-case skill dag-run was attempted; see failed_gates and receipt paths."
        ),
    }


def run_tau_embry_voice_control_skill_dag(
    session: dict[str, Any],
    *,
    tau_root: Path,
    agent_root: Path,
    skill_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    run_id = f"{utc_now().replace(':', '').replace('-', '')}-{session['id']}-{uuid4().hex[:8]}"
    run_root = Path("/tmp/chatterbox-fork-agent-out/embry-tau-skill-voice-control") / run_id
    spec_root = run_root / "specs"
    receipt_dir = run_root / "tau-run"
    run_root.mkdir(parents=True, exist_ok=True)
    dag_id = f"embry-{session['id']}"
    goal_hash = _sha256_text(json.dumps({"session_id": session["id"], "query": session.get("question")}, sort_keys=True))
    _write_tau_embry_voice_control_skill_spec(
        spec_root=spec_root,
        session=session,
        dag_id=dag_id,
        goal_hash=goal_hash,
        skill_root=skill_root,
        cwd=run_root,
    )
    reviewer_evidence = [
        {
            "kind": "reviewer_verdict",
            "reviewed_node_id": "embry-voice-control-skill-runner",
            "goal_hash": goal_hash,
            "verdict": "PASS",
        }
    ]
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-route-reviewer",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-route-reviewer",
            next_agent="human",
            evidence=reviewer_evidence,
        ),
        cwd=run_root,
    )
    contract_path = _write_tau_embry_voice_control_skill_contract(
        session=session,
        run_root=run_root,
        spec_root=spec_root,
        dag_id=dag_id,
        goal_hash=goal_hash,
    )
    command = [
        "uv",
        "run",
        "--project",
        str(tau_root),
        "tau",
        "dag-run",
        str(contract_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(agent_root),
        "--command-spec-root",
        str(spec_root),
    ]
    dag_run = run_cmd(command, timeout_s=timeout_s)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt: dict[str, Any] = {}
    skill_receipts = _find_skill_call_receipts(receipt_dir)
    skill_receipt_path = skill_receipts[0] if skill_receipts else None
    skill_receipt: dict[str, Any] = {}
    failed: list[str] = []
    if dag_run["returncode"] != 0:
        failed.append("tau_dag_run_command_ok")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        failed.append("tau_dag_receipt_read")
        receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if receipt.get("schema") != "tau.dag_receipt.v1":
        failed.append("tau_dag_receipt_schema")
    if receipt.get("ok") is not True:
        failed.append("tau_dag_receipt_ok")
    if receipt.get("status") != "PASS":
        failed.append("tau_dag_receipt_pass")
    selected_agents = receipt.get("selected_agents") if isinstance(receipt.get("selected_agents"), list) else []
    if selected_agents != ["embry-voice-control-skill-runner", "embry-route-reviewer"]:
        failed.append("tau_skill_selected_agents")
    if not receipt.get("command_loop_receipt"):
        failed.append("tau_skill_command_loop_receipt")
    if not skill_receipt_path:
        failed.append("skill_call_receipt_present")
    else:
        try:
            skill_receipt = json.loads(skill_receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failed.append("skill_call_receipt_read")
            skill_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if skill_receipt_path and skill_receipt.get("schema") != "skill.call.receipt.v1":
        failed.append("skill_call_receipt_schema")
    if skill_receipt_path and skill_receipt.get("skill_name") != "embry-voice-control":
        failed.append("skill_call_receipt_skill_name")
    if skill_receipt_path and skill_receipt.get("called_by") != "tau.dag_run.command_spec":
        failed.append("skill_called_by_tau_only")
    outputs = skill_receipt.get("outputs") if isinstance(skill_receipt.get("outputs"), dict) else {}
    if skill_receipt_path and not outputs.get("report_sha256"):
        failed.append("voice_control_report_hash_present")
    skill_failed_gates = skill_receipt.get("failed_gates") if isinstance(skill_receipt.get("failed_gates"), list) else []
    failed.extend(str(gate) for gate in skill_failed_gates)
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "required_skill": "embry-voice-control",
        "tau_dag_contract": str(contract_path),
        "tau_dag_receipt": str(receipt_path),
        "tau_command_loop_receipt": receipt.get("command_loop_receipt"),
        "skill_call_receipt": str(skill_receipt_path) if skill_receipt_path else None,
        "skill_call_receipt_sha256": _sha256_file(skill_receipt_path) if skill_receipt_path else None,
        "voice_control_report": outputs.get("report_path"),
        "voice_control_report_sha256": outputs.get("report_sha256"),
        "voice_control_overall_readiness": outputs.get("overall_readiness"),
        "voice_control_failed_case_ids": outputs.get("failed_case_ids"),
        "tau_dag_run": dag_run,
        "tau_dag_receipt_payload": receipt,
        "skill_call_receipt_payload": skill_receipt,
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": sorted(set(failed)),
        "observed": (
            "Tau dag-run invoked the embry-voice-control skill through a command spec and "
            "recorded its controlled-live readiness report."
            if not failed
            else "Tau invoked embry-voice-control controlled-live; see failed_gates and report path."
        ),
    }


def run_tau_agent_handoff_dag(
    session: dict[str, Any],
    *,
    tau_root: Path,
    agent_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    run_id = f"{utc_now().replace(':', '').replace('-', '')}-{session['id']}-{uuid4().hex[:8]}"
    run_root = Path("/tmp/chatterbox-fork-agent-out/embry-tau-dag-handoff") / run_id
    spec_root = run_root / "specs"
    receipt_dir = run_root / "tau-run"
    run_root.mkdir(parents=True, exist_ok=True)
    dag_id = f"embry-{session['id']}"
    goal_hash = _sha256_text(json.dumps({"session_id": session["id"], "query": session.get("question")}, sort_keys=True))
    router_evidence = [
        {
            "kind": "embry_tau_work_order",
            "matrix_session_id": session["id"],
            "route": route,
            "query": str(session.get("question") or ""),
            "goal_hash": goal_hash,
        }
    ]
    reviewer_evidence = [
        {
            "kind": "reviewer_verdict",
            "reviewed_node_id": "embry-request-router",
            "goal_hash": goal_hash,
            "verdict": "PASS",
        }
    ]
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-request-router",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-request-router",
            next_agent="embry-route-reviewer",
            evidence=router_evidence,
        ),
        cwd=run_root,
    )
    _write_tau_response_spec(
        spec_root=spec_root,
        agent="embry-route-reviewer",
        response=_tau_handoff_response(
            session=session,
            dag_id=dag_id,
            goal_hash=goal_hash,
            previous_subagent="embry-route-reviewer",
            next_agent="human",
            evidence=reviewer_evidence,
        ),
        cwd=run_root,
    )
    contract_path = _write_tau_handoff_contract(
        session=session,
        run_root=run_root,
        spec_root=spec_root,
        dag_id=dag_id,
        goal_hash=goal_hash,
    )
    command = [
        "uv",
        "run",
        "--project",
        str(tau_root),
        "tau",
        "dag-run",
        str(contract_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(agent_root),
        "--command-spec-root",
        str(spec_root),
    ]
    dag_run = run_cmd(command, timeout_s=timeout_s)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt: dict[str, Any] = {}
    failed: list[str] = []
    if dag_run["returncode"] != 0:
        failed.append("tau_dag_run_command_ok")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        failed.append("tau_dag_receipt_read")
        receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if receipt.get("schema") != "tau.dag_receipt.v1":
        failed.append("tau_dag_receipt_schema")
    if receipt.get("ok") is not True:
        failed.append("tau_dag_receipt_ok")
    if receipt.get("status") != "PASS":
        failed.append("tau_dag_receipt_pass")
    selected_agents = receipt.get("selected_agents") if isinstance(receipt.get("selected_agents"), list) else []
    if selected_agents != ["embry-request-router", "embry-route-reviewer"]:
        failed.append("tau_agent_handoff_selected_agents")
    if not receipt.get("command_loop_receipt"):
        failed.append("tau_agent_handoff_command_loop_receipt")
    reviewer_verdicts = receipt.get("reviewer_verdicts") if isinstance(receipt.get("reviewer_verdicts"), list) else []
    if not reviewer_verdicts or reviewer_verdicts[0].get("verdict") != "PASS":
        failed.append("tau_reviewer_verdict_pass")
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "tau_dag_contract": str(contract_path),
        "tau_dag_receipt": str(receipt_path),
        "tau_command_loop_receipt": receipt.get("command_loop_receipt"),
        "tau_dag_run": dag_run,
        "tau_dag_receipt_payload": receipt,
        "ok": not failed,
        "mocked": False,
        "live": True,
        "failed_gates": failed,
        "observed": (
            "Tau dag-run created a tau.dag_receipt.v1 and command-loop handoff receipt "
            "for this Embry stress matrix session."
            if not failed
            else "Tau dag-run was attempted for this Embry stress matrix session; see failed_gates and receipt paths."
        ),
    }


def run_tau_skill_preflight(
    session: dict[str, Any],
    *,
    tau_runner: Path,
    skill_root: Path,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    required_skill = required_skill_for_session(session)
    doctor = run_cmd([str(tau_runner), "doctor"], timeout_s=timeout_s)
    skill_path = skill_root / str(required_skill or "") / "SKILL.md"
    skill_exists = bool(required_skill and skill_path.exists())
    failed: list[str] = []
    if doctor["returncode"] != 0:
        failed.append("tau_doctor_command_ok")
    if not required_skill:
        failed.append("required_skill_declared")
    if not skill_exists:
        failed.append("required_skill_skill_md_exists")
    failed.extend(
        [
            "tau_agent_handoff_not_exercised",
            "skill_call_receipt_not_emitted",
            "tau_dag_receipt_not_created",
        ]
    )
    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": route,
        "required_skill": required_skill,
        "tau_doctor": doctor,
        "skill_preflight": {
            "skill_root": str(skill_root),
            "skill_path": str(skill_path) if required_skill else None,
            "skill_exists": skill_exists,
        },
        "ok": False,
        "mocked": False,
        "live": doctor["returncode"] == 0,
        "failed_gates": failed,
        "observed": (
            "Tau wrapper and required skill preflight ran, but no tau.agent_handoff.v1, "
            "tau.dag_receipt.v1, or skill.call.receipt.v1 was produced for this Embry direct-skill session."
        ),
    }


def run_turn_control_preflight(
    session: dict[str, Any],
    *,
    base_url: str,
    timeout_s: int,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    turn_id = f"matrix-turn-control-{uuid4().hex[:8]}"
    new_turn_id = f"matrix-new-turn-{uuid4().hex[:8]}"
    health = get_json(f"{base}/health", timeout_s)
    failed: list[str] = []
    if not health.get("ok_http") or not (health.get("json") or {}).get("ok"):
        failed.append("chatterbox_health_ok")

    requests = [
        (
            "cancel",
            f"{base}/turn/{turn_id}/cancel",
            {"reason": "matrix interruption preflight", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "duck",
            f"{base}/playback/{turn_id}/duck",
            {"reason": "matrix interruption preflight", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "stop",
            f"{base}/playback/{turn_id}/stop",
            {"reason": "matrix interruption preflight", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
    ]
    responses: list[dict[str, Any]] = []
    for action, url, payload in requests:
        response = post_json(url, payload, timeout_s)
        responses.append({"action": action, "request": payload, "response": response})
        body = response.get("json") if isinstance(response.get("json"), dict) else {}
        if not response.get("ok_http") or not body.get("ok"):
            failed.append(f"{action}_response_ok")
        control = body.get("control") if isinstance(body.get("control"), dict) else {}
        if control.get("turn_id") != turn_id:
            failed.append(f"{action}_turn_id_matches")

    final_body = responses[-1].get("response", {}).get("json") if responses else {}
    final_control = final_body.get("control") if isinstance(final_body, dict) and isinstance(final_body.get("control"), dict) else {}
    action_order = [event.get("action") for event in final_control.get("events") or [] if isinstance(event, dict)]
    if action_order[-3:] != ["cancel", "duck", "stop"]:
        failed.append("control_event_order")
    if not final_control.get("cancelled"):
        failed.append("cancelled_state_true")
    if not final_control.get("stale_chunks_should_skip"):
        failed.append("stale_chunks_should_skip_true")
    if not final_control.get("ducked"):
        failed.append("ducked_state_true")
    if not final_control.get("stopped"):
        failed.append("stopped_state_true")

    question = normalize(str(session.get("question") or ""))
    if "blessed qra" in question or "cached response" in question:
        scenario_failed = [
            "blessed_qra_cached_response_not_exercised",
            "stale_audio_stream_bytes_not_measured",
            "interruption_detected_receipt_not_emitted",
        ]
    elif "non primary" in question or "non-primary" in str(session.get("question") or "").lower():
        scenario_failed = [
            "non_primary_interrupt_rejection_not_exercised",
            "speaker_gate_receipt_not_linked_to_turn_control",
            "interruption_detected_receipt_not_emitted",
        ]
    elif "tau tool wait" in question or "natural stop" in question:
        scenario_failed = [
            "tau_tool_wait_not_exercised",
            "natural_stop_phrase_not_observed",
            "interruption_detected_receipt_not_emitted",
        ]
    else:
        scenario_failed = [
            "new_horus_turn_not_exercised",
            "new_turn_wins_receipt_not_emitted",
            "interruption_detected_receipt_not_emitted",
        ]
    failed.extend(scenario_failed)

    return {
        "id": session["id"],
        "matrix_session": session,
        "query": str(session.get("question") or ""),
        "route": str(session.get("route") or ""),
        "health": health,
        "turn_id": turn_id,
        "new_turn_id": new_turn_id,
        "responses": responses,
        "final_control": final_control,
        "action_order": action_order,
        "endpoint_preflight_ok": not [gate for gate in failed if gate.endswith("_ok") or gate.endswith("_matches") or gate.endswith("_true") or gate == "control_event_order"],
        "ok": False,
        "mocked": False,
        "live": bool(health.get("ok_http")),
        "failed_gates": sorted(set(failed)),
        "observed": (
            "Chatterbox cancel/duck/stop endpoint state was exercised, but this matrix case still lacks "
            "a live interruption-detection receipt, linked audio playback evidence, and new-turn outcome proof."
        ),
    }


def speaker_resolution_payload(session: dict[str, Any]) -> dict[str, Any]:
    question = normalize(str(session.get("question") or ""))
    base = {
        "speaker_evidence_id": f"embry-stress-matrix-{session['id']}",
        "session_id": "embry-stress-matrix",
        "turn_id": str(session["id"]),
        "persona_id": "embry",
        "threshold": DEFAULT_SPEAKER_RESOLVE_THRESHOLD,
        "ambiguity_margin": DEFAULT_SPEAKER_AMBIGUITY_MARGIN,
        "allow_personal_memory": True,
    }
    if "known horus" in question or "clean audio" in question:
        base["candidates"] = [
            {
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": 0.93,
                "source": "embry_stress_matrix_clean_horus_probe",
                "tags": ["persona:horus_lupercal", "speaker:horus_lupercal", "user:horus_lupercal"],
            }
        ]
    elif "female distractor" in question or "overlaps horus" in question:
        base["candidates"] = [
            {
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": 0.88,
                "source": "embry_stress_matrix_overlap_probe",
                "tags": ["persona:horus_lupercal"],
            },
            {
                "speaker_id": "female_distractor",
                "display_name": "Female Distractor",
                "confidence": 0.87,
                "source": "embry_stress_matrix_overlap_probe",
                "tags": ["speaker:female_distractor"],
            },
        ]
    elif "ambiguous" in question:
        base["candidates"] = [
            {
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": 0.80,
                "source": "embry_stress_matrix_low_confidence_probe",
                "tags": ["persona:horus_lupercal"],
            },
            {
                "speaker_id": "unknown_other",
                "display_name": "Unknown Other",
                "confidence": 0.78,
                "source": "embry_stress_matrix_low_confidence_probe",
                "tags": [],
            },
        ]
    else:
        base["candidates"] = []
    return base


def classify_speaker_resolution(session: dict[str, Any], resolution: dict[str, Any]) -> list[str]:
    if not resolution.get("ok_http"):
        return ["speaker_resolve_http_ok"]
    payload = resolution.get("json") if isinstance(resolution.get("json"), dict) else {}
    question = normalize(str(session.get("question") or ""))
    failed: list[str] = []
    if payload.get("schema") != "memory.speaker_resolution.v1":
        failed.append("speaker_resolution_schema")

    if "known horus" in question or "clean audio" in question:
        if payload.get("status") != "known":
            failed.append("speaker_resolution_status_known")
        if payload.get("speaker_id") != "horus_lupercal":
            failed.append("speaker_resolution_horus_lupercal")
        if payload.get("allow_personal_memory") is not True:
            failed.append("speaker_resolution_allows_personal_memory")
        memory_tags = payload.get("memory_tags") if isinstance(payload.get("memory_tags"), list) else []
        for tag in ["speaker:horus_lupercal", "user:horus_lupercal", "persona:horus_lupercal"]:
            if tag not in memory_tags:
                failed.append(f"speaker_resolution_memory_tag_{tag.replace(':', '_')}")
    elif "female distractor" in question or "overlaps horus" in question:
        if payload.get("status") != "ambiguous":
            failed.append("speaker_resolution_status_ambiguous")
        if payload.get("speaker_id") is not None:
            failed.append("speaker_resolution_no_authoritative_speaker")
        if payload.get("allow_personal_memory") is not False:
            failed.append("speaker_resolution_blocks_personal_memory")
        if not payload.get("identity_prompt"):
            failed.append("speaker_resolution_identity_prompt_present")
    elif "ambiguous" in question:
        if payload.get("status") not in {"unknown", "ambiguous"}:
            failed.append("speaker_resolution_status_unknown_or_ambiguous")
        if payload.get("speaker_id") is not None:
            failed.append("speaker_resolution_no_authoritative_speaker")
        if payload.get("allow_personal_memory") is not False:
            failed.append("speaker_resolution_blocks_personal_memory")
        if not payload.get("identity_prompt"):
            failed.append("speaker_resolution_identity_prompt_present")
    else:
        if payload.get("status") != "unknown":
            failed.append("speaker_resolution_status_unknown")
        if payload.get("allow_personal_memory") is not False:
            failed.append("speaker_resolution_blocks_personal_memory")
        identity_prompt = payload.get("identity_prompt") if isinstance(payload.get("identity_prompt"), dict) else {}
        if not identity_prompt.get("text"):
            failed.append("speaker_resolution_identity_prompt_text")
        if int(identity_prompt.get("count") or 0) < 20:
            failed.append("speaker_resolution_identity_prompt_bank_20")
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
    tau_runner: Path,
    tau_root: Path = DEFAULT_TAU_ROOT,
    agent_root: Path = DEFAULT_AGENT_ROOT,
    chatterbox_url: str = DEFAULT_CHATTERBOX_URL,
    skill_root: Path = DEFAULT_SKILL_ROOT,
    timeout_s: int,
) -> dict[str, Any]:
    route = str(session.get("route") or "")
    query = str(session.get("question") or "")
    if route == "memory.speaker.resolve":
        speaker_resolution = post_json(
            f"{memory_url.rstrip('/')}/speaker/resolve",
            speaker_resolution_payload(session),
            timeout_s,
        )
        failed = classify_speaker_resolution(session, speaker_resolution)
        return {
            "id": session["id"],
            "matrix_session": session,
            "query": query,
            "route": route,
            "speaker_resolution": speaker_resolution,
            "ok": not failed,
            "mocked": False,
            "live": bool(speaker_resolution.get("ok_http")),
            "failed_gates": failed,
        }
    if route == "tau.agent_handoff":
        return run_tau_agent_handoff_dag(
            session,
            tau_root=tau_root,
            agent_root=agent_root,
            timeout_s=timeout_s,
        )
    if route == "tau.skill.analytics":
        return run_tau_analytics_skill_dag(
            session,
            tau_root=tau_root,
            agent_root=agent_root,
            skill_root=skill_root,
            timeout_s=timeout_s,
        )
    if route == "tau.skill.create_evidence_case":
        return run_tau_create_evidence_case_skill_dag(
            session,
            tau_root=tau_root,
            agent_root=agent_root,
            skill_root=skill_root,
            timeout_s=timeout_s,
        )
    if route == "tau.skill.create_figure":
        return run_tau_create_figure_skill_dag(
            session,
            tau_root=tau_root,
            agent_root=agent_root,
            skill_root=skill_root,
            timeout_s=timeout_s,
        )
    if route == "tau.skill.embry_voice_control":
        return run_tau_embry_voice_control_skill_dag(
            session,
            tau_root=tau_root,
            agent_root=agent_root,
            skill_root=skill_root,
            timeout_s=timeout_s,
        )
    if route.startswith("tau.skill."):
        return run_tau_skill_preflight(session, tau_runner=tau_runner, skill_root=skill_root, timeout_s=timeout_s)
    if route == "chatterbox.turn_control":
        return run_turn_control_preflight(session, base_url=chatterbox_url, timeout_s=timeout_s)
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
    parser.add_argument("--tau-runner", default=DEFAULT_TAU_RUNNER, type=Path)
    parser.add_argument("--tau-root", default=DEFAULT_TAU_ROOT, type=Path)
    parser.add_argument("--agent-root", default=DEFAULT_AGENT_ROOT, type=Path)
    parser.add_argument("--chatterbox-url", default=DEFAULT_CHATTERBOX_URL)
    parser.add_argument("--skill-root", default=DEFAULT_SKILL_ROOT, type=Path)
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
                tau_runner=args.tau_runner,
                tau_root=args.tau_root,
                agent_root=args.agent_root,
                chatterbox_url=args.chatterbox_url,
                skill_root=args.skill_root,
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
