import argparse
import json
from pathlib import Path

from scripts import embry_voice_control as evc


def test_new_session_creates_receipt_directories_and_event_file(tmp_path: Path) -> None:
    receipt = evc.new_session(tmp_path, session_id="ses_test")

    assert receipt["ok"] is True
    assert receipt["live"] is True
    assert receipt["mocked"] is False
    assert Path(receipt["events_path"]).exists()
    assert Path(receipt["receipts_dir"]).is_dir()
    assert Path(receipt["artifacts_dir"]).is_dir()
    assert (tmp_path / "ses_test" / "receipts" / "session_start_receipt.json").exists()


def test_child_status_preserves_live_and_mocked_fields(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    status = evc.child_status(
        {
            "schema": "example.v1",
            "ok": True,
            "live": True,
            "mocked": False,
            "failed_gates": [],
        },
        path=path,
    )

    assert status == {
        "ok": True,
        "live": True,
        "mocked": False,
        "path": str(path),
        "failed_gates": [],
        "schema": "example.v1",
    }


def test_os_loopback_core_receipt_is_honest_about_non_unified_turn_id(monkeypatch, tmp_path: Path) -> None:
    def fake_run_cmd(cmd, *, timeout, env=None):  # noqa: ANN001
        joined = " ".join(str(part) for part in cmd)
        if "rung1_audio_graph_realtimestt.py" in joined:
            out = Path(cmd[cmd.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "captured.wav").write_bytes(b"RIFFfake")
            evc.write_json(
                out / "rung_receipt.json",
                {
                    "schema": "embry.rung1.audio_graph_realtimestt.v1",
                    "ok": True,
                    "live": True,
                    "mocked": False,
                    "failed_gates": [],
                },
            )
        elif "rung2_source_audio_speaker_gate.py" in joined:
            out_root = Path(cmd[cmd.index("--out-root") + 1])
            run_id = cmd[cmd.index("--run-id") + 1]
            out = out_root / run_id
            out.mkdir(parents=True, exist_ok=True)
            evc.write_json(
                out / "rung2_source_audio_speaker_gate_receipt.json",
                {
                    "schema": "embry.rung2_source_audio_speaker_gate.v1",
                    "ok": True,
                    "live": True,
                    "mocked": False,
                    "failed_gates": [],
                },
            )
        return {"argv": cmd, "returncode": 0, "elapsed_ms": 1.0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(evc, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(evc, "command_versions", lambda: {"python": "test"})
    monkeypatch.setattr(evc, "resolve_whisper_api_key", lambda env: {"present": True, "source": "test", "env_name": "WHISPER_API_KEY"})

    receipt = evc.check_os_loopback_core(
        argparse.Namespace(
            session_root=tmp_path,
            session_id="ses_receipt",
            nonce="alpha",
            expected_phrase="Horus check",
            stage_timeout_s=10.0,
            realtimestt_timeout_s=10.0,
            core_timeout_s=10.0,
            with_speaker_gate=True,
            with_memory_tau=False,
            child_python=Path("python3"),
            speaker_gate_python=Path("python3"),
        )
    )

    assert receipt["ok"] is True
    assert receipt["live"] is True
    assert receipt["mocked"] is False
    assert "single_turn_id_across_all_voice_services" in receipt["does_not_prove"]
    assert Path(receipt["events_path"]).exists()
    assert Path(receipt["receipt_path"]).exists()
    assert json.loads(Path(receipt["receipt_path"]).read_text())["event_journal_sha256"] == receipt["event_journal_sha256"]
