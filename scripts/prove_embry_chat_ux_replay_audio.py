#!/usr/bin/env python3
"""Create a browser media-playback receipt for Embry Chat UX session replay."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


DEFAULT_URL = "http://localhost:3002/#embry-voice"
DEFAULT_OUT_ROOT = Path("/tmp/chatterbox-fork-agent-out/embry-chat-ux-replay-audio")
DEFAULT_LATEST = DEFAULT_OUT_ROOT / "latest" / "receipt.json"
DEFAULT_CHROMIUM = "/snap/bin/chromium"
DEFAULT_SESSION_TITLE = "Embry / Horus voice"


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def summarize_audio_events(events: list[dict[str, Any]], *, min_advanced_seconds: float) -> dict[str, Any]:
    play_events = [event for event in events if event.get("ev") == "play"]
    playing_events = [event for event in events if event.get("ev") == "playing"]
    time_updates = [event for event in events if event.get("ev") == "timeupdate"]
    ended_events = [event for event in events if event.get("ev") == "ended"]
    error_events = [event for event in events if event.get("ev") == "error"]
    waiting_events = [event for event in events if event.get("ev") in {"waiting", "stalled"}]
    current_times = [
        value
        for value in (_finite(event.get("currentTime")) for event in time_updates)
        if value is not None
    ]
    max_current_time = max(current_times) if current_times else 0.0
    durations = [
        value
        for value in (_finite(event.get("duration")) for event in events)
        if value is not None and value > 0
    ]
    max_duration = max(durations) if durations else None
    ended_or_expected_offset = bool(ended_events) or (
        max_duration is not None and max_current_time >= max(0.0, max_duration - 0.35)
    )
    first_play_t = _finite(play_events[0].get("t")) if play_events else None
    last_progress_t = _finite(time_updates[-1].get("t")) if time_updates else None
    cut_off_after_ms = None
    if first_play_t is not None and last_progress_t is not None and not ended_or_expected_offset:
        cut_off_after_ms = max(0.0, last_progress_t - first_play_t)

    return {
        "playback_started": bool(play_events),
        "playing_event_seen": bool(playing_events),
        "current_time_advanced": max_current_time >= min_advanced_seconds,
        "ended_or_played_to_expected_offset": ended_or_expected_offset,
        "cut_off_after_ms": cut_off_after_ms,
        "event_count": len(events),
        "play_event_count": len(play_events),
        "playing_event_count": len(playing_events),
        "timeupdate_event_count": len(time_updates),
        "ended_event_count": len(ended_events),
        "error_event_count": len(error_events),
        "waiting_or_stalled_event_count": len(waiting_events),
        "max_current_time_seconds": round(max_current_time, 3),
        "max_duration_seconds": round(max_duration, 3) if max_duration is not None else None,
        "srcs": sorted({str(event.get("src")) for event in events if event.get("src")}),
    }


def build_receipt(
    *,
    run_id: str,
    url: str,
    headed: bool,
    wait_ms: int,
    min_advanced_seconds: float,
    audio_count: int,
    visible_text: str,
    events: list[dict[str, Any]],
    screenshot_path: Path,
    session_title: str,
    session_title_count: int,
    replay_button_count: int,
) -> dict[str, Any]:
    audible_playback = summarize_audio_events(events, min_advanced_seconds=min_advanced_seconds)
    failed_gates: list[str] = []
    if session_title_count != 1:
        failed_gates.append("canonical_session_row_not_unique")
    if replay_button_count != 1:
        failed_gates.append("canonical_session_replay_button_not_unique")
    if audio_count <= 0:
        failed_gates.append("audio_elements_not_present")
    if not audible_playback["playback_started"]:
        failed_gates.append("browser_audio_playback_not_started")
    if not audible_playback["playing_event_seen"]:
        failed_gates.append("browser_audio_playing_event_missing")
    if not audible_playback["current_time_advanced"]:
        failed_gates.append("browser_audio_current_time_did_not_advance")
    if not audible_playback["ended_or_played_to_expected_offset"]:
        failed_gates.append("browser_audio_did_not_reach_expected_offset")
    if audible_playback["error_event_count"]:
        failed_gates.append("browser_audio_error_event_seen")
    if audible_playback["cut_off_after_ms"] is not None:
        failed_gates.append("browser_audio_cut_off_before_expected_offset")

    return {
        "schema": "chatterbox.embry_chat_ux_replay_audio_receipt.v1",
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "used_ui": True,
        "url": url,
        "selected_session_title": session_title,
        "selected_session_title_count": session_title_count,
        "selected_session_replay_button_count": replay_button_count,
        "headed": headed,
        "wait_ms": wait_ms,
        "min_advanced_seconds": min_advanced_seconds,
        "audio_count": audio_count,
        "screenshot": str(screenshot_path),
        "visible_text_excerpt": visible_text[:2000],
        "audible_playback_receipt": audible_playback,
        "browser_audio_playback": audible_playback,
        "audio_events": events,
        "failed_gates": failed_gates,
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "claims": {
            "proves": [
                "shared_chat_replay_starts_browser_media_playback_and_current_time_advances"
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "physical speaker audibility",
                "RealtimeSTT audio ingress",
                "speaker identity correctness",
                "memory/Tau answer correctness",
                "Chatterbox generation correctness",
            ],
        },
    }


def run_probe(
    *,
    url: str,
    out_dir: Path,
    headed: bool,
    wait_ms: int,
    min_advanced_seconds: float,
    chromium: str,
    session_title: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = out_dir / "replay-audio.png"
    receipt_path = out_dir / "receipt.json"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not headed,
            executable_path=chromium if Path(chromium).exists() else None,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.evaluate(
            """() => {
              window.__embryAudioEvents = [];
              const clean = (value) => Number.isFinite(value) ? value : null;
              const hook = (audio, idx) => {
                if (audio.__embryReceiptHooked) return;
                audio.__embryReceiptHooked = true;
                ['play','playing','timeupdate','pause','ended','error','stalled','waiting','canplay'].forEach((ev) => {
                  audio.addEventListener(ev, () => window.__embryAudioEvents.push({
                    ev,
                    idx,
                    t: Date.now(),
                    currentTime: clean(audio.currentTime),
                    duration: clean(audio.duration),
                    paused: audio.paused,
                    src: audio.currentSrc || audio.src || null,
                    error: audio.error ? audio.error.message : null
                  }));
                });
              };
              new MutationObserver(() => document.querySelectorAll('audio').forEach(hook))
                .observe(document.body, { childList: true, subtree: true });
              document.querySelectorAll('audio').forEach(hook);
            }"""
        )
        title = page.get_by_text(session_title, exact=True)
        session_title_count = title.count()
        replay_button = title.locator("xpath=../..").locator(
            '[data-qid="embry-voice:session-play"]'
        )
        replay_button_count = replay_button.count() if session_title_count == 1 else 0
        if replay_button_count == 1:
            replay_button.click(timeout=10000)
            page.wait_for_timeout(wait_ms)
        audio_count = page.locator("audio").count()
        events = page.evaluate("window.__embryAudioEvents || []")
        visible_text = page.locator("body").inner_text(timeout=5000)
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    receipt = build_receipt(
        run_id=out_dir.name,
        url=url,
        headed=headed,
        wait_ms=wait_ms,
        min_advanced_seconds=min_advanced_seconds,
        audio_count=audio_count,
        visible_text=visible_text,
        events=events,
        screenshot_path=screenshot_path,
        session_title=session_title,
        session_title_count=session_title_count,
        replay_button_count=replay_button_count,
    )
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DEFAULT_LATEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(receipt_path, DEFAULT_LATEST)
    return receipt_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--run-id", default=_utc_run_id())
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=9000)
    parser.add_argument("--min-advanced-seconds", type=float, default=1.0)
    parser.add_argument("--chromium", default=DEFAULT_CHROMIUM)
    parser.add_argument("--session-title", default=DEFAULT_SESSION_TITLE)
    args = parser.parse_args()

    receipt = run_probe(
        url=args.url,
        out_dir=args.out_root / args.run_id,
        headed=args.headed,
        wait_ms=args.wait_ms,
        min_advanced_seconds=args.min_advanced_seconds,
        chromium=args.chromium,
        session_title=args.session_title,
    )
    print(receipt)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
