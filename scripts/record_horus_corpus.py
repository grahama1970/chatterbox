#!/usr/bin/env python3
"""Guided capture of the Horus voice corpora.

Two corpora with deliberately different requirements:

  clone  - clean close-mic source for Chatterbox voice conditioning.
           Quality dominates: high sample rate, quiet room, close talk.

  verify - deployment-matched samples for the resemblyzer speaker gate.
           Realism dominates: captured through the same device and at the
           same distance the live campaign uses.

Never merge them. A clone trained on Jabra-at-distance audio sounds like the
Jabra; a speaker profile enrolled on close-mic audio will not match live turns.

Usage:
    python3 scripts/record_horus_corpus.py shootout
    python3 scripts/record_horus_corpus.py record --corpus clone  --device plughw:3,0
    python3 scripts/record_horus_corpus.py record --corpus verify --device plughw:4,0
    python3 scripts/record_horus_corpus.py record --corpus impostor --device plughw:4,0 --speaker alice
"""

from __future__ import annotations

import argparse
import audioop
import json
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO / "persona_dream_voice_refs" / "horus_corpus"

# Phonetically balanced public-domain material (Harvard sentences / Rainbow Passage).
NEUTRAL = [
    "The birch canoe slid on the smooth planks.",
    "Glue the sheet to the dark blue background.",
    "It's easy to tell the depth of a well.",
    "These days a chicken leg is a rare dish.",
    "Rice is often served in round bowls.",
    "The juice of lemons makes fine punch.",
    "The box was thrown beside the parked truck.",
    "The hogs were fed chopped corn and garbage.",
    "Four hours of steady work faced us.",
    "A large size in stockings is hard to sell.",
    "When the sunlight strikes raindrops in the air, they act as a prism and "
    "form a rainbow.",
    "The rainbow is a division of white light into many beautiful colors.",
    "These take the shape of a long round arch, with its path high above, and "
    "its two ends apparently beyond the horizon.",
    "There is, according to legend, a boiling pot of gold at one end.",
    "People look, but no one ever finds it.",
]

# Tone lines matching the stress matrix's required conversation tones.
TONES = {
    "frustrated": [
        "I have asked you three times already and it still is not working.",
        "This is the same problem as yesterday. Why did nothing change?",
        "I don't have time to keep repeating myself about this.",
        "Just tell me what actually went wrong, please.",
    ],
    "hostile": [
        "That answer is useless and you know it.",
        "Stop wasting my time with excuses.",
        "I don't care what the log says, it's wrong.",
        "Fix it now or I'm shutting this down.",
    ],
    "discouraged": [
        "I don't think this is ever going to work.",
        "Maybe we should just give up on the whole approach.",
        "I've been at this for hours and I'm getting nowhere.",
        "It feels like every fix breaks something else.",
    ],
    "playful": [
        "Alright, let's see if you can actually surprise me this time.",
        "Not bad. I might even let you keep your job.",
        "Okay that was genuinely clever, I'll give you that one.",
        "Come on, you can do better than that.",
    ],
}

# Held-out lines: never used for enrollment, only for verification.
HELD_OUT = [
    "The pipe began to rust while new.",
    "Open the crate but don't break the glass.",
    "Add the sum to the product of these three.",
    "Thieves who rob friends deserve jail.",
    "The ripe taste of cheese improves with age.",
]

ENROLL = [
    "Hey Embry, what is the capital of Japan?",
    "Hey Embry, show me the compliance status for the current control set.",
    "Hey Embry, summarize what we worked on yesterday.",
    "Hey Embry, run the analytics figure for last week's numbers.",
    "Hey Embry, what did I ask you to remember about the deployment?",
]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def analyze(path: Path) -> dict:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        channels = handle.getnchannels()
        rate = handle.getframerate()
        count = handle.getnframes()
    if channels == 2:
        frames = audioop.tomono(frames, 2, 0.5, 0.5)
    seconds = count / rate if rate else 0.0
    peak = audioop.max(frames, 2)
    return {
        "seconds": round(seconds, 2),
        "rate": rate,
        "rms": audioop.rms(frames, 2),
        "peak": peak,
        "clipping": peak >= 32700,
    }


def record(device: str, seconds: int, rate: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "arecord", "-D", device, "-d", str(seconds),
            "-f", "S16_LE", "-r", str(rate), "-c", "1", str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def verdict(stats: dict) -> tuple[bool, str]:
    """Accept/reject a take on objective level criteria."""
    if stats["clipping"]:
        return False, "CLIPPING - back off from the mic or lower gain"
    if stats["rms"] < 800:
        return False, f"TOO QUIET (rms {stats['rms']}) - move closer or speak up"
    if stats["rms"] > 12000:
        return False, f"TOO HOT (rms {stats['rms']}) - back off slightly"
    return True, f"good (rms {stats['rms']}, peak {stats['peak']})"


def cmd_shootout(args: argparse.Namespace) -> int:
    """Record the same phrase on every candidate input, rank by headroom."""
    cards = subprocess.run(
        ["arecord", "-l"], capture_output=True, text=True, check=False
    ).stdout
    devices = []
    for line in cards.splitlines():
        if line.startswith("card "):
            card = line.split(":")[0].split()[1]
            dev = line.split("device ")[1].split(":")[0].strip()
            label = line.split("[")[1].split("]")[0] if "[" in line else line
            devices.append((f"plughw:{card},{dev}", label))

    print("Candidate inputs:")
    for dev, label in devices:
        print(f"  {dev:16s} {label}")
    print(
        f"\nFor each device you will read one sentence ({args.seconds}s).\n"
        "Sit at the distance you would ACTUALLY use for that device.\n"
    )
    results = []
    for dev, label in devices:
        input(f"\n--- {dev} ({label}) --- press ENTER, then read: "
              f"'{NEUTRAL[0]}' ")
        out = OUT_ROOT / "shootout" / f"{dev.replace(':', '_').replace(',', '_')}.wav"
        try:
            record(dev, args.seconds, 48000, out)
        except subprocess.CalledProcessError:
            print(f"    UNAVAILABLE (device busy or unsupported)")
            continue
        stats = analyze(out)
        results.append((dev, label, stats))
        print(f"    rms={stats['rms']:6d} peak={stats['peak']:6d} "
              f"clipping={stats['clipping']}")

    if results:
        best = max(results, key=lambda r: r[2]["rms"] if not r[2]["clipping"] else 0)
        print(f"\nHighest clean level: {best[0]} ({best[1]})")
        print("Pick the CLONE device by clean level + low noise; use the Jabra "
              "for VERIFY regardless, since that is the live campaign path.")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    stamp = utc_stamp()
    session = OUT_ROOT / args.corpus / stamp
    session.mkdir(parents=True, exist_ok=True)

    if args.corpus == "clone":
        rate, seconds = 48000, 12
        plan = [("neutral", line) for line in NEUTRAL]
        for tone, lines in TONES.items():
            plan += [(tone, line) for line in lines]
        guidance = (
            "CLONE SOURCE — close mic (6-12 in), quiet room.\n"
            "Read naturally. For tone sections, actually perform the emotion;\n"
            "flat readings produce a clone that cannot do tone."
        )
    elif args.corpus == "verify":
        rate, seconds = 16000, 10
        plan = [("enroll", line) for line in ENROLL]
        plan += [("heldout", line) for line in HELD_OUT]
        guidance = (
            "VERIFICATION — normal seated distance, through the Jabra.\n"
            "Do NOT lean in. This must match how you really talk to Embry."
        )
    else:  # impostor
        rate, seconds = 16000, 10
        plan = [("impostor", line) for line in ENROLL[:3] + HELD_OUT[:2]]
        guidance = (
            f"IMPOSTOR — a DIFFERENT person than Horus ({args.speaker}).\n"
            "Same device and distance as the verify corpus."
        )

    print(f"\n{'=' * 68}\n{guidance}\n{'=' * 68}")
    print(f"device={args.device} rate={rate}Hz takes={len(plan)} -> {session}\n")

    manifest = []
    for index, (label, line) in enumerate(plan, start=1):
        while True:
            print(f"\n[{index}/{len(plan)}] ({label})")
            print(f'    "{line}"')
            input(f"    ENTER to record {seconds}s, then speak... ")
            name = f"{index:03d}_{label}.wav"
            dest = session / name
            record(args.device, seconds, rate, dest)
            stats = analyze(dest)
            ok, note = verdict(stats)
            print(f"    -> {note}")
            if ok:
                manifest.append({"file": name, "label": label, "text": line, **stats})
                break
            if input("    Retake? [Y/n] ").strip().lower() == "n":
                manifest.append({"file": name, "label": label, "text": line,
                                 "accepted_with_warning": note, **stats})
                break

    meta = {
        "schema": "embry.horus_corpus.v1",
        "corpus": args.corpus,
        "speaker": args.speaker,
        "synthetic": False,
        "provenance": "physical_human_recording",
        "device": args.device,
        "rate": rate,
        "captured_at": stamp,
        "takes": manifest,
    }
    (session / "manifest.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone. {len(manifest)} takes -> {session}")
    print(f"Manifest: {session / 'manifest.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    shoot = sub.add_parser("shootout", help="rank available mics by clean level")
    shoot.add_argument("--seconds", type=int, default=6)
    shoot.set_defaults(func=cmd_shootout)

    rec = sub.add_parser("record", help="guided corpus capture")
    rec.add_argument("--corpus", choices=["clone", "verify", "impostor"], required=True)
    rec.add_argument("--device", required=True, help="e.g. plughw:3,0")
    rec.add_argument("--speaker", default="horus")
    rec.set_defaults(func=cmd_record)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
