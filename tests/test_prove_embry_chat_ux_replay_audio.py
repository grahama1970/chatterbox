from pathlib import Path

from scripts.prove_embry_chat_ux_replay_audio import build_receipt, summarize_audio_events


def test_summarize_audio_events_accepts_started_advanced_and_ended_playback() -> None:
    events = [
        {"ev": "play", "t": 1000, "currentTime": 0, "duration": None, "src": "/a.wav"},
        {"ev": "playing", "t": 1010, "currentTime": 0.01, "duration": 3.6, "src": "/a.wav"},
        {"ev": "timeupdate", "t": 1300, "currentTime": 1.2, "duration": 3.6, "src": "/a.wav"},
        {"ev": "ended", "t": 4700, "currentTime": 3.6, "duration": 3.6, "src": "/a.wav"},
    ]

    summary = summarize_audio_events(events, min_advanced_seconds=1.0)

    assert summary["playback_started"] is True
    assert summary["playing_event_seen"] is True
    assert summary["current_time_advanced"] is True
    assert summary["ended_or_played_to_expected_offset"] is True
    assert summary["cut_off_after_ms"] is None


def test_summarize_audio_events_marks_cutoff_when_playback_never_reaches_expected_offset() -> None:
    events = [
        {"ev": "play", "t": 1000, "currentTime": 0, "duration": 5.0, "src": "/a.wav"},
        {"ev": "playing", "t": 1010, "currentTime": 0.01, "duration": 5.0, "src": "/a.wav"},
        {"ev": "timeupdate", "t": 1100, "currentTime": 0.05, "duration": 5.0, "src": "/a.wav"},
    ]

    summary = summarize_audio_events(events, min_advanced_seconds=1.0)

    assert summary["playback_started"] is True
    assert summary["current_time_advanced"] is False
    assert summary["ended_or_played_to_expected_offset"] is False
    assert summary["cut_off_after_ms"] == 100.0


def test_build_receipt_fails_without_audio_progress() -> None:
    receipt = build_receipt(
        run_id="test",
        url="http://localhost:3002/#embry-voice",
        headed=False,
        wait_ms=1000,
        min_advanced_seconds=1.0,
        audio_count=1,
        visible_text="Embry Voice",
        events=[{"ev": "play", "t": 1000, "currentTime": 0, "duration": 5.0, "src": "/a.wav"}],
        screenshot_path=Path("/tmp/replay-audio.png"),
    )

    assert receipt["ok"] is False
    assert "browser_audio_current_time_did_not_advance" in receipt["failed_gates"]
    assert "browser_audio_did_not_reach_expected_offset" in receipt["failed_gates"]


def test_build_receipt_passes_with_browser_media_events() -> None:
    receipt = build_receipt(
        run_id="test",
        url="http://localhost:3002/#embry-voice",
        headed=False,
        wait_ms=5000,
        min_advanced_seconds=1.0,
        audio_count=1,
        visible_text="Embry Voice",
        events=[
            {"ev": "play", "t": 1000, "currentTime": 0, "duration": 3.0, "src": "/a.wav"},
            {"ev": "playing", "t": 1010, "currentTime": 0.01, "duration": 3.0, "src": "/a.wav"},
            {"ev": "timeupdate", "t": 2500, "currentTime": 1.5, "duration": 3.0, "src": "/a.wav"},
            {"ev": "ended", "t": 4000, "currentTime": 3.0, "duration": 3.0, "src": "/a.wav"},
        ],
        screenshot_path=Path("/tmp/replay-audio.png"),
    )

    assert receipt["ok"] is True
    assert receipt["audible_playback_receipt"]["playback_started"] is True
    assert receipt["audible_playback_receipt"]["current_time_advanced"] is True
    assert receipt["failed_gates"] == []
