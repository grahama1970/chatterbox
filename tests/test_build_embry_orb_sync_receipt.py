import json
from pathlib import Path

from scripts.build_embry_orb_sync_receipt import build_receipt


def test_build_orb_sync_receipt_from_direct_speak_proof(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFFfake-wave")
    screenshot = tmp_path / "orb.png"
    screenshot.write_bytes(b"fake-png")
    source = tmp_path / "proof.json"
    source.write_text(
        json.dumps(
            {
                "maxLevel": 0.615,
                "samples": [
                    {
                        "orbSpeechBound": "false",
                        "orbAudioLevel": "0.000",
                        "orbState": "synthesizing",
                    },
                    {
                        "orbSpeechBound": "true",
                        "orbAudioLevel": "0.615",
                        "orbState": "speaking",
                    },
                ],
                "result": {
                    "startedAtMs": 1783361300926,
                    "audioAuthority": {
                        "authority": "server-chatterbox-wav-envelope-v1",
                        "artifactId": "audio-123",
                        "url": "/chatterbox-artifacts/audio-123.wav",
                        "path": str(audio),
                        "sha256": "a" * 64,
                        "durationMs": 5280,
                        "localPlayback": {
                            "startedAtEpochMs": 1783361300926,
                            "driver": "pipewire-pw-play",
                            "command": "pw-play",
                            "target": "auto",
                            "pid": 123,
                        },
                        "envelope": {
                            "frames": [
                                {"t": 0, "level": 0},
                                {"t": 0.016, "level": 0.615},
                            ]
                        },
                    },
                },
            }
        )
    )

    receipt = build_receipt(source, screenshot)

    assert receipt["ok"] is True
    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["turn_id"] == "audio-123"
    assert receipt["audio_artifact_id"] == "audio-123"
    assert receipt["playback"]["audio_artifact_id"] == "audio-123"
    assert receipt["playback"]["started_at_epoch_ms"] == 1783361300926
    assert receipt["orb"]["authority"] == "server-envelope"
    assert receipt["orb"]["envelope_frame_count"] == 2
    assert receipt["orb"]["max_level"] == 0.615
    assert receipt["orb"]["nonzero_audio_sample_count"] == 1
    assert receipt["orb"]["bound_sample_count"] == 1
    assert receipt["failed_gates"] == []
