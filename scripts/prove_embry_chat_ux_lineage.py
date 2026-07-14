#!/usr/bin/env python3
"""Create a live DOM receipt for Embry Chat UX turn/audio/entity lineage."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


DEFAULT_URL = "http://localhost:3002/#embry-voice"
DEFAULT_OUT_ROOT = Path("/tmp/chatterbox-fork-agent-out/embry-chat-ux-lineage")
DEFAULT_LATEST = DEFAULT_OUT_ROOT / "latest" / "receipt.json"
DEFAULT_CHROMIUM = "/snap/bin/chromium"
DEFAULT_SESSION_TITLE = "Embry / Horus voice"


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_receipt(
    *,
    run_id: str,
    url: str,
    chat_messages: list[dict[str, Any]],
    audio_artifacts: list[dict[str, Any]],
    screenshot_path: Path,
    session_title: str,
    session_title_count: int,
    replay_button_count: int,
) -> dict[str, Any]:
    assistant_messages = [
        message for message in chat_messages if message.get("qid") == "shared-chat:message:assistant"
    ]
    assistant_with_audio = [
        message for message in assistant_messages if message.get("audio_artifact_count", 0) > 0
    ]
    assistant_with_turn_id = [
        message for message in assistant_with_audio if message.get("turn_id")
    ]
    assistant_with_entities = [
        message for message in assistant_messages if message.get("entity_span_count", 0) > 0
    ]
    audio_with_turn_id = [audio for audio in audio_artifacts if audio.get("turn_id")]
    same_turn_audio = [
        audio
        for audio in audio_with_turn_id
        if audio.get("turn_id") in {message.get("turn_id") for message in assistant_with_turn_id}
    ]

    failed_gates: list[str] = []
    if session_title_count != 1:
        failed_gates.append("canonical_session_row_not_unique")
    if replay_button_count != 1:
        failed_gates.append("canonical_session_replay_button_not_unique")
    if not assistant_messages:
        failed_gates.append("shared_chat_assistant_message_missing")
    if not audio_artifacts:
        failed_gates.append("shared_chat_audio_artifact_missing")
    if not assistant_with_audio:
        failed_gates.append("assistant_message_audio_artifact_missing")
    if not assistant_with_turn_id:
        failed_gates.append("assistant_message_turn_id_missing")
    if not audio_with_turn_id:
        failed_gates.append("audio_artifact_turn_id_missing")
    if not same_turn_audio:
        failed_gates.append("chat_text_audio_same_turn_id_not_proven")
    if not assistant_with_entities:
        failed_gates.append("entity_underlines_not_rendered_in_assistant_message")

    lineage_ready = not {
        "assistant_message_turn_id_missing",
        "audio_artifact_turn_id_missing",
        "chat_text_audio_same_turn_id_not_proven",
    }.intersection(failed_gates)
    entity_underlines_ready = "entity_underlines_not_rendered_in_assistant_message" not in failed_gates

    return {
        "schema": "chatterbox.embry_chat_ux_lineage_probe.v1",
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "used_ui": True,
        "url": url,
        "selected_session_title": session_title,
        "selected_session_title_count": session_title_count,
        "selected_session_replay_button_count": replay_button_count,
        "screenshot": str(screenshot_path),
        "chat_message_count": len(chat_messages),
        "assistant_message_count": len(assistant_messages),
        "audio_artifact_count": len(audio_artifacts),
        "assistant_with_audio_count": len(assistant_with_audio),
        "assistant_with_turn_id_count": len(assistant_with_turn_id),
        "audio_with_turn_id_count": len(audio_with_turn_id),
        "assistant_with_entity_span_count": len(assistant_with_entities),
        "lineage_ready": lineage_ready,
        "entity_underlines_ready": entity_underlines_ready,
        "chat_messages": chat_messages,
        "audio_artifacts": audio_artifacts,
        "failed_gates": failed_gates,
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "claims": {
            "proves": [
                "shared_chat_assistant_turn_audio_and_entity_underlines_share_dom_lineage"
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "assistant.response.plan.v1 backend receipt exists",
                "chat.render.receipt.v1 backend receipt exists",
                "RealtimeSTT audio ingress",
                "speaker identity correctness",
                "physical speaker audibility",
            ],
        },
    }


def run_probe(*, url: str, out_dir: Path, chromium: str, session_title: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = out_dir / "lineage.png"
    receipt_path = out_dir / "receipt.json"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=chromium if Path(chromium).exists() else None,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=20000)
        title = page.get_by_text(session_title, exact=True)
        session_title_count = title.count()
        replay_button = title.locator("xpath=../..").locator(
            '[data-qid="embry-voice:session-play"]'
        )
        replay_button_count = replay_button.count() if session_title_count == 1 else 0
        if replay_button_count == 1:
            replay_button.click(timeout=10000)
            page.wait_for_timeout(2500)
        payload = page.evaluate(
            """() => {
              const attrMap = (el) => Object.fromEntries([...el.attributes].map((a) => [a.name, a.value]));
              const messageForAudio = (audio) => audio.closest('[data-qid^="shared-chat:message"]');
              const chatMessages = [...document.querySelectorAll('[data-qid^="shared-chat:message"]')].map((el, idx) => {
                const attrs = attrMap(el);
                const audios = [...el.querySelectorAll('audio')];
                return {
                  index: idx,
                  qid: attrs['data-qid'] || null,
                  branch: attrs['data-branch'] || null,
                  turn_id: attrs['data-turn-id'] || attrs['data-turnid'] || attrs['data-message-id'] || null,
                  response_plan_id: attrs['data-response-plan-id'] || null,
                  chat_render_receipt_id: attrs['data-chat-render-receipt-id'] || null,
                  entity_span_count: Number(attrs['data-entity-span-count'] || 0),
                  audio_artifact_count: audios.length,
                  audio_srcs: audios.map((audio) => audio.currentSrc || audio.src || null),
                  text: (el.innerText || el.textContent || '').trim().slice(0, 1000)
                };
              });
              const audioArtifacts = [...document.querySelectorAll('audio')].map((audio, idx) => {
                const attrs = attrMap(audio);
                const message = messageForAudio(audio);
                const messageAttrs = message ? attrMap(message) : {};
                return {
                  index: idx,
                  qid: attrs['data-qid'] || null,
                  turn_id: attrs['data-turn-id'] || attrs['data-turnid'] || attrs['data-message-id'] || null,
                  parent_message_qid: messageAttrs['data-qid'] || null,
                  parent_turn_id: messageAttrs['data-turn-id'] || messageAttrs['data-turnid'] || messageAttrs['data-message-id'] || null,
                  embry_session_audio: attrs['data-embry-session-audio'] || null,
                  embry_replay_text: attrs['data-embry-replay-text'] || null,
                  src: audio.currentSrc || audio.src || null
                };
              });
              return { chatMessages, audioArtifacts };
            }"""
        )
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    receipt = build_receipt(
        run_id=out_dir.name,
        url=url,
        chat_messages=payload["chatMessages"],
        audio_artifacts=payload["audioArtifacts"],
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
    parser.add_argument("--chromium", default=DEFAULT_CHROMIUM)
    parser.add_argument("--session-title", default=DEFAULT_SESSION_TITLE)
    args = parser.parse_args()

    receipt = run_probe(
        url=args.url,
        out_dir=args.out_root / args.run_id,
        chromium=args.chromium,
        session_title=args.session_title,
    )
    print(receipt)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
