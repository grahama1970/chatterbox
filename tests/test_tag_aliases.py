#!/usr/bin/env python3
"""Expressive tag alias expansion (owner request 2026-11-14: far more emotion tags).

Why aliases and not new token ids: the Turbo text embedding is [50276, 1024]
(text_emb / text_head / tfmr.wte) and ids 50257-50275 are exactly the 19 installed
tags, so there are zero free rows. A new id would be an untrained embedding row -
noise, not a tag. So expressive names expand onto the nearest NATIVE tag and the
substitution is recorded in the render receipt instead of being silent.

These checks are structural and deterministic: no service, no GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.presets import (  # noqa: E402
    ALIAS_TAG_VOCABULARY,
    CHATTERBOX_EVENT_TAGS,
    TAG_ALIASES,
    expand_tag_aliases,
    plan_tag_expansion,
)

CHECKS = 0
FAILS: list[str] = []

#: The 19 tags the loaded Turbo tokenizer actually consumes.
INSTALLED_TAGS = {
    "[advertisement]", "[angry]", "[chuckle]", "[clear throat]", "[cough]",
    "[crying]", "[dramatic]", "[fear]", "[gasp]", "[groan]", "[happy]",
    "[laugh]", "[narration]", "[sarcastic]", "[shush]", "[sigh]", "[sniff]",
    "[surprised]", "[whispering]",
}


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(f"{label} {detail}".strip())
        print(f"  FAIL {label} {detail}")


def main() -> int:
    # --- the table itself -------------------------------------------------
    check("alias table is non-trivial", len(TAG_ALIASES) >= 40, str(len(TAG_ALIASES)))
    check("every alias is bracket-shaped",
          all(a.startswith("[") and a.endswith("]") and a == a.lower() for a in TAG_ALIASES),
          str([a for a in TAG_ALIASES if not a.startswith("[")][:3]))
    unknown = sorted({v for v in TAG_ALIASES.values()} - INSTALLED_TAGS)
    check("every alias target is an INSTALLED native tag", not unknown, str(unknown))
    check("no alias shadows a native tag name",
          not (set(TAG_ALIASES) & INSTALLED_TAGS),
          str(sorted(set(TAG_ALIASES) & INSTALLED_TAGS))[:120])
    check("vocabulary is longest-first",
          list(ALIAS_TAG_VOCABULARY) == sorted(TAG_ALIASES, key=len, reverse=True))
    check("the owner's own example is present", "[hearty laugh]" in TAG_ALIASES)

    # --- expansion behaviour ---------------------------------------------
    text = "She laughed [hearty laugh] and then a [sob] before [unknown tag] stayed."
    out, applied = expand_tag_aliases(text)
    check("alias rewritten to native", out ==
          "She laughed [laugh] and then a [crying] before [unknown tag] stayed.", repr(out))
    check("applied list records both", applied ==
          [{"alias": "[hearty laugh]", "native": "[laugh]"},
           {"alias": "[sob]", "native": "[crying]"}], repr(applied))
    check("unknown tag left intact (spoken literally, not dropped)", "[unknown tag]" in out)
    check("surrounding prose untouched", out.startswith("She laughed ") and "stayed." in out)

    # case-insensitivity
    out2, applied2 = expand_tag_aliases("[HEARTY LAUGH] yes")
    check("uppercase alias expands", out2.startswith("[laugh]"), repr(out2))
    check("uppercase alias recorded lowercase", applied2[0]["alias"] == "[hearty laugh]")

    # idempotence: native text is unchanged and records nothing
    native = "He [laugh] then [sigh] then [whispering]."
    out3, applied3 = expand_tag_aliases(native)
    check("native text unchanged", out3 == native)
    check("no expansion recorded for native tags", applied3 == [])

    # empty / None
    check("None is a no-op", expand_tag_aliases(None) == (None, []))
    check("empty is a no-op", expand_tag_aliases("") == ("", []))

    # duplicate alias appears once in the applied list
    out4, applied4 = expand_tag_aliases("[sob] and again [sob]")
    check("repeated alias applied once", len(applied4) == 1, repr(applied4))
    check("repeated alias rewritten twice", out4 == "[crying] and again [crying]", repr(out4))

    # ---- F2: expansion is GATED on a backend that consumes event tags (review 2026-11-14)
    # A backend that speaks bracket tokens literally must receive the text UNCHANGED: rewriting
    # `[hearty laugh]` to `[laugh]` there mutates words the model was going to say out loud.
    gated_text, gated_applied = plan_tag_expansion("[hearty laugh] then prose.", "chatterbox_base_affect")
    check("F2 a literal-tag backend receives the text UNCHANGED",
          gated_text == "[hearty laugh] then prose.", repr(gated_text))
    check("F2 no expansion is recorded for a literal-tag backend", gated_applied == [], repr(gated_applied))

    turbo_text, turbo_applied = plan_tag_expansion("[hearty laugh] then prose.", "chatterbox_turbo")
    check("F2 a tag-consuming backend still gets the native tag", turbo_text == "[laugh] then prose.", repr(turbo_text))
    check("F2 the consuming backend records the expansion",
          turbo_applied == [{"alias": "[hearty laugh]", "native": "[laugh]"}], repr(turbo_applied))

    unknown_text, unknown_applied = plan_tag_expansion("[hearty laugh]", "no_such_backend")
    check("F2 an UNKNOWN backend is treated as non-consuming (fail-visible, no rewrite)",
          unknown_text == "[hearty laugh]" and unknown_applied == [], repr(unknown_text))

    # no alias is a substring-shadow of another (longest-first safety)
    shadowed = [a for a in TAG_ALIASES
                if any(b != a and a in b for b in TAG_ALIASES)]
    check("no alias is a substring of another alias", not shadowed, str(shadowed[:3]))

    # event tags remain a subset of installed tags (regression guard)
    check("CHATTERBOX_EVENT_TAGS are all installed",
          set(CHATTERBOX_EVENT_TAGS) <= INSTALLED_TAGS,
          str(sorted(set(CHATTERBOX_EVENT_TAGS) - INSTALLED_TAGS)))

    # LIVE cross-check against the running Turbo tokenizer (skip if service down):
    # the hardcoded INSTALLED_TAGS set must equal the server's accepted_tags,
    # which are read from the loaded tokenizer at startup (set_runtime_tag_vocabulary).
    try:
        import json as _json
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:8018/health", timeout=5) as resp:
            live_tags = _json.load(resp)["tag_handling"]["accepted_tags"]
        check("live tokenizer vocabulary == INSTALLED_TAGS (sorted)",
              sorted(live_tags) == sorted(INSTALLED_TAGS),
              f"live_only={sorted(set(live_tags) - INSTALLED_TAGS)} static_only={sorted(INSTALLED_TAGS - set(live_tags))}")
        check("every alias target is in the LIVE tokenizer vocabulary",
              set(TAG_ALIASES.values()) <= set(live_tags),
              str(sorted(set(TAG_ALIASES.values()) - set(live_tags))[:120]))
    except Exception as exc:  # noqa: BLE001 - live probe is best-effort
        print(f"  SKIP live vocabulary probe ({exc.__class__.__name__}: {exc})")

    print(f"{CHECKS - len(FAILS)}/{CHECKS} checks passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
