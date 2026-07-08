from scripts.build_embry_stress_session_matrix import build_matrix
from scripts.smoke_embry_intelligence_stress import (
    classify_answer,
    classify_matrix_answer,
    classify_speaker_resolution,
    classify_voice_delivery_intent,
    run_matrix_session,
    select_matrix_sessions,
    speaker_resolution_payload,
)


def answer_payload(text: str, *, can_answer: bool = True) -> dict:
    return {
        "ok_http": True,
        "json": {
            "can_answer": can_answer,
            "final_response": text,
        },
    }


def test_sparta_qra_acceptance_rejects_unrelated_control_exclusion() -> None:
    failed = classify_answer(
        {"kind": "sparta_qra_acceptance"},
        answer_payload("S0609 is a terminal NON_GENERATION QRA coverage outcome."),
    )

    assert "sparta_qra_answer_overfit_to_unrelated_control_exclusion" in failed
    assert "sparta_qra_answer_missing_acceptance_terms" in failed


def test_persona_memory_requires_expected_terms() -> None:
    failed = classify_answer(
        {"kind": "expected_terms", "expected_terms": ["cthonia"]},
        answer_payload("Build and operate the Horus TTS pipeline."),
    )

    assert failed == ["persona_memory_answer_wrong_or_unrelated"]


def test_memory_miss_must_not_return_unrelated_answer() -> None:
    failed = classify_answer(
        {"kind": "memory_miss"},
        answer_payload("Read and explain Embry OS configuration from embry.yaml."),
    )

    assert failed == ["memory_miss_should_not_answer_unrelated_record"]


def test_memory_miss_allows_no_answer() -> None:
    failed = classify_answer(
        {"kind": "memory_miss"},
        answer_payload("", can_answer=False),
    )

    assert failed == []


def test_matrix_answer_rejects_persona_memory_from_skill_collection() -> None:
    failed = classify_matrix_answer(
        {"route": "memory.persona_memory", "question": "What did Horus last ask Embry about voice testing?"},
        {
            "ok_http": True,
            "json": {
                "can_answer": True,
                "final_response": "Build and operate the Horus TTS pipeline.",
                "sources": [{"source": "skill_descriptions", "key": "skill_tts-horus"}],
            },
        },
    )

    assert "persona_memory_answer_uses_unrelated_source_collection" in failed


def test_matrix_sparta_rejects_control_exclusion_for_any_qra_question() -> None:
    failed = classify_matrix_answer(
        {"route": "memory.sparta_qra", "question": "What should Embry do when a SPARTA QRA has weak evidence?"},
        answer_payload("S0609 is recorded as a terminal NON_GENERATION QRA coverage outcome."),
    )

    assert "sparta_qra_answer_overfit_to_unrelated_control_exclusion" in failed


def test_matrix_answer_marks_unsupported_route_unimplemented() -> None:
    failed = classify_matrix_answer(
        {"route": "tau.agent_handoff", "question": "Ask Tau to create an evidence-case."},
        answer_payload(""),
    )

    assert failed == ["runner_route_not_implemented"]


def intent_payload(tone: str, *, source: str = "memory_intent", delivery_stage: str = "satisfied") -> dict:
    return {
        "ok_http": True,
        "json": {
            "voice_delivery": {
                "source": source,
                "tone": tone,
                "delivery_stage": delivery_stage,
            },
        },
    }


def test_voice_delivery_intent_rejects_generic_memory_confident_for_overlap() -> None:
    failed = classify_voice_delivery_intent(
        {
            "route": "memory.intent.voice_delivery",
            "question": "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
        },
        intent_payload("memory_confident"),
    )

    assert "voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt" in failed


def test_voice_delivery_intent_accepts_one_at_a_time_overlap_tone() -> None:
    failed = classify_voice_delivery_intent(
        {
            "route": "memory.intent.voice_delivery",
            "question": "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
        },
        intent_payload("one_at_a_time_interrupt", delivery_stage="boundary"),
    )

    assert failed == []


def test_tau_agent_handoff_route_runs_tau_preflight_but_fails_without_handoff(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run_cmd(cmd: list[str], *, timeout_s: int) -> dict:
        calls.append((cmd, timeout_s))
        return {
            "cmd": cmd,
            "returncode": 0,
            "elapsed_ms": 1.0,
            "stdout_tail": '{"ok": true}',
            "stderr_tail": "",
        }

    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.run_cmd", fake_run_cmd)

    result = run_matrix_session(
        {"id": "tau_tool_orchestration-simple-01", "route": "tau.agent_handoff", "question": "Ask Tau to create an evidence-case."},
        memory_url="http://127.0.0.1:8601",
        brave_script=tmp_path / "brave.py",
        tau_runner=tmp_path / "tau-run.sh",
        timeout_s=30,
    )

    assert calls == [([str(tmp_path / "tau-run.sh"), "doctor"], 30)]
    assert result["ok"] is False
    assert result["live"] is True
    assert result["failed_gates"] == ["tau_agent_handoff_not_exercised"]


def test_tau_direct_skill_route_checks_skill_but_fails_without_receipts(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run_cmd(cmd: list[str], *, timeout_s: int) -> dict:
        calls.append((cmd, timeout_s))
        return {
            "cmd": cmd,
            "returncode": 0,
            "elapsed_ms": 1.0,
            "stdout_tail": '{"ok": true}',
            "stderr_tail": "",
        }

    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "create-figure"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# create-figure\n", encoding="utf-8")
    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.run_cmd", fake_run_cmd)

    result = run_matrix_session(
        {
            "id": "skill_create_figure-simple-01",
            "route": "tau.skill.create_figure",
            "question": "Ask Embry to create a figure.",
            "expected_route": {"required_skill": "create-figure"},
            "oracle": {"required_skill": "create-figure"},
        },
        memory_url="http://127.0.0.1:8601",
        brave_script=tmp_path / "brave.py",
        tau_runner=tmp_path / "tau-run.sh",
        skill_root=skill_root,
        timeout_s=30,
    )

    assert calls == [([str(tmp_path / "tau-run.sh"), "doctor"], 30)]
    assert result["ok"] is False
    assert result["live"] is True
    assert result["required_skill"] == "create-figure"
    assert result["skill_preflight"]["skill_exists"] is True
    assert result["failed_gates"] == [
        "tau_agent_handoff_not_exercised",
        "skill_call_receipt_not_emitted",
        "tau_dag_receipt_not_created",
    ]


def test_tau_direct_skill_route_fails_missing_skill_file(monkeypatch, tmp_path) -> None:
    def fake_run_cmd(cmd: list[str], *, timeout_s: int) -> dict:
        return {
            "cmd": cmd,
            "returncode": 0,
            "elapsed_ms": 1.0,
            "stdout_tail": '{"ok": true}',
            "stderr_tail": "",
        }

    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.run_cmd", fake_run_cmd)

    result = run_matrix_session(
        {
            "id": "skill_missing-simple-01",
            "route": "tau.skill.missing",
            "question": "Ask Embry to call a missing skill.",
            "expected_route": {"required_skill": "missing-skill"},
            "oracle": {"required_skill": "missing-skill"},
        },
        memory_url="http://127.0.0.1:8601",
        brave_script=tmp_path / "brave.py",
        tau_runner=tmp_path / "tau-run.sh",
        skill_root=tmp_path / "skills",
        timeout_s=30,
    )

    assert "required_skill_skill_md_exists" in result["failed_gates"]
    assert result["skill_preflight"]["skill_exists"] is False


def test_chatterbox_turn_control_route_exercises_endpoints_but_fails_without_interruption_receipts(
    monkeypatch,
    tmp_path,
) -> None:
    posts = []

    def fake_get_json(url: str, timeout_s: int) -> dict:
        return {"ok_http": True, "json": {"ok": True}, "elapsed_ms": 1.0, "url": url}

    def fake_post_json(url: str, payload: dict, timeout_s: int) -> dict:
        posts.append((url, payload, timeout_s))
        action = "cancel" if "/cancel" in url else "duck" if "/duck" in url else "stop"
        events = [{"action": item} for item in ["cancel", "duck", "stop"][: len(posts)]]
        return {
            "ok_http": True,
            "json": {
                "ok": True,
                "control": {
                    "turn_id": payload["old_turn_id"],
                    "events": events,
                    "cancelled": len(posts) >= 1,
                    "stale_chunks_should_skip": len(posts) >= 1,
                    "ducked": len(posts) >= 2,
                    "stopped": len(posts) >= 3,
                },
            },
        }

    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.get_json", fake_get_json)
    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.post_json", fake_post_json)

    result = run_matrix_session(
        {
            "id": "interruption-simple-01",
            "route": "chatterbox.turn_control",
            "question": "Interrupt Embry mid-answer with a new Horus question.",
        },
        memory_url="http://127.0.0.1:8601",
        brave_script=tmp_path / "brave.py",
        tau_runner=tmp_path / "tau-run.sh",
        chatterbox_url="http://127.0.0.1:8018",
        timeout_s=30,
    )

    assert [post[0].rsplit("/", 1)[-1] for post in posts] == ["cancel", "duck", "stop"]
    assert result["endpoint_preflight_ok"] is True
    assert result["live"] is True
    assert result["ok"] is False
    assert "new_horus_turn_not_exercised" in result["failed_gates"]
    assert "new_turn_wins_receipt_not_emitted" in result["failed_gates"]
    assert "interruption_detected_receipt_not_emitted" in result["failed_gates"]


def test_speaker_resolution_payload_known_horus_uses_speaker_tags() -> None:
    payload = speaker_resolution_payload(
        {
            "id": "speaker_identity-simple-01",
            "question": "Known Horus asks for personal memory with clean audio.",
        }
    )

    assert payload["candidates"][0]["speaker_id"] == "horus_lupercal"
    assert "speaker:horus_lupercal" in payload["candidates"][0]["tags"]
    assert payload["threshold"] == 0.82
    assert payload["allow_personal_memory"] is True


def test_speaker_resolution_classifies_known_horus_pass() -> None:
    failed = classify_speaker_resolution(
        {
            "id": "speaker_identity-simple-01",
            "question": "Known Horus asks for personal memory with clean audio.",
        },
        {
            "ok_http": True,
            "json": {
                "schema": "memory.speaker_resolution.v1",
                "status": "known",
                "speaker_id": "horus_lupercal",
                "allow_personal_memory": True,
                "memory_tags": ["persona:horus_lupercal", "speaker:horus_lupercal", "user:horus_lupercal"],
            },
        },
    )

    assert failed == []


def test_speaker_resolution_classifies_overlap_must_fail_closed() -> None:
    failed = classify_speaker_resolution(
        {
            "id": "speaker_identity-simple-04",
            "question": "Female distractor overlaps Horus and must not become memory authority.",
        },
        {
            "ok_http": True,
            "json": {
                "schema": "memory.speaker_resolution.v1",
                "status": "known",
                "speaker_id": "horus_lupercal",
                "allow_personal_memory": True,
                "identity_prompt": None,
            },
        },
    )

    assert failed == [
        "speaker_resolution_blocks_personal_memory",
        "speaker_resolution_identity_prompt_present",
        "speaker_resolution_no_authoritative_speaker",
        "speaker_resolution_status_ambiguous",
    ]


def test_speaker_resolution_route_calls_memory_speaker_resolve(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_post_json(url: str, payload: dict, timeout_s: int) -> dict:
        calls.append((url, payload, timeout_s))
        return {
            "ok_http": True,
            "json": {
                "schema": "memory.speaker_resolution.v1",
                "status": "unknown",
                "speaker_id": None,
                "allow_personal_memory": False,
                "identity_prompt": {"text": "Who am I speaking with?", "count": 20},
            },
        }

    monkeypatch.setattr("scripts.smoke_embry_intelligence_stress.post_json", fake_post_json)

    result = run_matrix_session(
        {
            "id": "speaker_identity-simple-02",
            "route": "memory.speaker.resolve",
            "question": "Unknown speaker asks for Horus memory and must be asked to identify.",
        },
        memory_url="http://127.0.0.1:8601",
        brave_script=tmp_path / "brave.py",
        tau_runner=tmp_path / "tau-run.sh",
        timeout_s=30,
    )

    assert calls[0][0] == "http://127.0.0.1:8601/speaker/resolve"
    assert calls[0][1]["candidates"] == []
    assert result["ok"] is True
    assert result["mocked"] is False
    assert result["live"] is True


def test_select_matrix_sessions_filters_folder_difficulty_and_limit() -> None:
    selected = select_matrix_sessions(
        build_matrix(),
        folder="sparta_qra_compliance",
        difficulty="simple",
        offset=0,
        limit=2,
    )

    assert [session["id"] for session in selected] == [
        "sparta_qra_compliance-simple-01",
        "sparta_qra_compliance-simple-02",
    ]


def test_select_matrix_sessions_applies_offset_after_filters() -> None:
    selected = select_matrix_sessions(
        build_matrix(),
        folder=None,
        difficulty="simple",
        offset=16,
        limit=2,
    )

    assert [session["id"] for session in selected] == [
        "tau_tool_orchestration-simple-01",
        "tau_tool_orchestration-simple-02",
    ]
