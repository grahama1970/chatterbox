#!/home/graham/workspace/experiments/chatterbox/.venv/bin/python
"""Agentic eval: Chatterbox emotional-quality and variety gate.

This is the focused entry point for the retained emotional-quality eval. It
reuses the live render and waveform gates from ``eval_tone_audibility`` but keeps
that case addressable without running the broader tone/pace matrix harness.

The result is a voice-quality artifact, not emotion truth: it measures rendered
pause realization, clipping, signal, pitch variation, duration, and
cross-utterance acoustic variety for tender, guarded, and playful utterances.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval_tone_audibility import DEFAULT_BASE_URL, run_emotional_quality_variety


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out-root", default=str(Path(__file__).resolve().parent.parent / "logs"))
    parser.add_argument("--out", type=Path, help="write the case JSON result for independent eval read-back")
    args = parser.parse_args()

    try:
        result = run_emotional_quality_variety(args.base_url, Path(args.out_root))
    except Exception as exc:  # noqa: BLE001 - infrastructure failure must be distinct from measured failure
        print(json.dumps({"case": "emotional_quality_variety", "error": f"{type(exc).__name__}: {exc}"}))
        return 2

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    print(f"RESULT: {'PASS' if result['pass'] else 'FAIL'} (emotional_quality_variety)")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
