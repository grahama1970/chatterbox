from pathlib import Path

from scripts.smoke_continuous_voice_loop import first_event_ms, overlap_assessment, transport_receipt_for_input_wav


def test_first_event_ms_returns_first_matching_event() -> None:
    receipt = {
        "events": [
            {"type": "other", "elapsed_ms": 1.0},
            {"type": "realtimestt.vad_start", "elapsed_ms": 12.5},
            {"type": "realtimestt.vad_start", "elapsed_ms": 99.0},
        ]
    }

    assert first_event_ms(receipt, "realtimestt.vad_start") == 12.5
    assert first_event_ms(receipt, "missing") is None


def test_overlap_assessment_records_anonymous_pyannote_and_segment_evidence() -> None:
    assessment = overlap_assessment(
        pyannote_receipt={
            "summary": {
                "speaker_count": 2,
                "speakers": ["SPEAKER_00", "SPEAKER_01"],
                "overlap_seconds": 0.5,
            }
        },
        speaker_receipt={
            "summary": {
                "voiced_segment_count": 10,
                "horus_segment_count": 8,
                "embry_segment_count": 1,
            }
        },
        min_overlap_seconds=0.25,
        max_embry_ratio=0.2,
    )

    assert assessment["pyannote_overlap_candidate"] is True
    assert assessment["non_embry_overlap_candidate"] is True
    assert assessment["response_text"] == "Hey, one at a time?"
    assert assessment["segment_horus_count"] == 8
    assert assessment["segment_embry_count"] == 1
    assert assessment["anonymous_pyannote_speakers"] == ["SPEAKER_00", "SPEAKER_01"]


def test_overlap_assessment_does_not_assign_identity_from_pyannote_labels() -> None:
    assessment = overlap_assessment(
        pyannote_receipt={
            "summary": {
                "speaker_count": 2,
                "speakers": ["SPEAKER_00", "SPEAKER_01"],
                "overlap_seconds": 0.5,
            }
        },
        speaker_receipt={
            "summary": {
                "voiced_segment_count": 10,
                "horus_segment_count": 5,
                "embry_segment_count": 5,
            }
        },
        min_overlap_seconds=0.25,
        max_embry_ratio=0.2,
    )

    assert assessment["pyannote_overlap_candidate"] is True
    assert assessment["non_embry_overlap_candidate"] is False
    assert assessment["response_text"] is None
    assert assessment["policy"] == "fail_closed_before_personal_recall_when_multiple_non_embry_speakers_overlap"


def test_transport_receipt_for_input_wav_is_explicit_about_existing_capture(tmp_path: Path) -> None:
    audio = tmp_path / "capture.wav"
    audio.write_bytes(b"RIFFfake")

    receipt = transport_receipt_for_input_wav(audio, source="pipewire_monitor")

    assert receipt["ok"] is True
    assert receipt["mocked"] is False
    assert receipt["source"] == "pipewire_monitor"
    assert receipt["artifacts"]["wav"] == str(audio)
    assert "fresh_browser_getusermedia_capture_in_this_runner" in receipt["claims"]["does_not_prove"]
