"""Sanity tests for reusable voice-cache selection metadata.

These tests avoid model inference. They check the deterministic policy layer
that chooses cached wait, ETA, and interruption utterances before playback.
"""

from __future__ import annotations

import unittest

from chatterbox.agent.conversation import (
    ETA_RESPONSE_RULES,
    HUM_INTERSTITIALS,
    INTERRUPTION_ACKNOWLEDGEMENTS,
    LOW_BUFFER_FILLERS,
    WAIT_ENTERTAINMENT_ACTIVITIES,
    WAIT_RESPONSE_RULES,
    acknowledgement_for_interrupt,
    eta_responses_for_expected_delay,
    has_internal_terms,
    wait_entertainment_for_context,
    wait_decision_for_expected_delay,
    wait_responses_for_expected_delay,
)
from scripts.pre_render_voice_cache import cache_usages, render_cache_entries


class VoiceCachePolicyTest(unittest.TestCase):
    def test_interruption_acknowledgement_variants_are_available(self) -> None:
        self.assertGreaterEqual(len(INTERRUPTION_ACKNOWLEDGEMENTS), 20)
        self.assertEqual(acknowledgement_for_interrupt("wait, new question", 1), "Okay, switching.")
        self.assertEqual(acknowledgement_for_interrupt("stop", 0), "Okay, stopping.")
        for text in INTERRUPTION_ACKNOWLEDGEMENTS:
            self.assertFalse(has_internal_terms(text), text)

    def test_wait_response_policy_maps_delay_to_human_phrase(self) -> None:
        self.assertEqual(wait_responses_for_expected_delay(500), [])
        self.assertIn("Hmm.", wait_responses_for_expected_delay(900))
        self.assertIn("I'm looking now.", wait_responses_for_expected_delay(2500))
        self.assertIn("I have enough to start.", wait_responses_for_expected_delay(6500))
        long_wait = wait_responses_for_expected_delay(9000)
        self.assertIn("This will take a little while. You can grab coffee if you want.", long_wait)

    def test_eta_response_policy_does_not_cancel_work(self) -> None:
        self.assertIn("About another second.", eta_responses_for_expected_delay(900))
        self.assertIn("Probably three to five more seconds.", eta_responses_for_expected_delay(3000))
        self.assertIn("Probably under ten seconds.", eta_responses_for_expected_delay(9000))
        self.assertIn("This may take a bit longer. I'll keep checking in.", eta_responses_for_expected_delay(20000))

    def test_wait_decision_can_start_hum_for_long_waits(self) -> None:
        decision = wait_decision_for_expected_delay(9000, variant_offset=4)
        self.assertEqual(decision["text"], "This will take a little while. You can grab coffee if you want.")
        self.assertTrue(decision["should_speak"])
        self.assertFalse(decision["should_start_hum"])
        self.assertEqual(decision["wait_activity"]["id"], "count_primes")
        self.assertEqual(decision["wait_activity"]["kind"], "chatterbox_voice")
        self.assertTrue(decision["wait_activity"]["interruptible"])
        self.assertEqual(decision["hum"]["channel"], "voice_interstitial")
        self.assertTrue(decision["hum"]["start_muted"])
        self.assertEqual(decision["hum"]["volume"], 0.25)
        self.assertEqual(decision["hum"]["fade_in_after"], "speech_finishes")
        self.assertEqual(decision["hum"]["duck_when"], ["speech_starts", "user_interrupts"])
        self.assertEqual(decision["hum"]["selection"]["mode"], "persona_cache")
        self.assertTrue(decision["hum"]["selection"]["allow_singing"])
        self.assertTrue(decision["hum"]["selection"]["avoid_forbidden"])
        self.assertFalse(decision["hum"]["interstitials"]["enabled"])
        self.assertTrue(decision["hum"]["interstitials"]["can_interrupt_hum"])
        self.assertTrue(decision["hum"]["interstitials"]["keeps_existing_work_alive"])
        self.assertIn("[chuckle]", decision["hum"]["interstitials"]["texts"])

    def test_wait_entertainment_supports_multiple_idle_behaviors(self) -> None:
        ids = {activity["id"] for activity in WAIT_ENTERTAINMENT_ACTIVITIES}
        self.assertGreaterEqual(
            ids,
            {"soft_hum", "low_singing", "mouth_beatbox", "count_primes", "plain_presence"},
        )
        for activity in WAIT_ENTERTAINMENT_ACTIVITIES:
            self.assertIn(activity["kind"], {"cached_audio", "chatterbox_voice"})
            self.assertIn("mood_tags", activity)
            self.assertIn("tone_tags", activity)
            self.assertIn("avoid_when", activity)

    def test_wait_entertainment_can_choose_cached_singing_for_long_waits(self) -> None:
        activity = wait_entertainment_for_context(13000, conversation_tone="casual", variant_offset=1)
        self.assertIsNotNone(activity)
        self.assertEqual(activity["id"], "low_singing")
        self.assertEqual(activity["kind"], "cached_audio")
        self.assertEqual(activity["channel"], "singing")

    def test_wait_decision_records_when_singing_is_disallowed(self) -> None:
        decision = wait_decision_for_expected_delay(13000, variant_offset=1, allow_singing=False)

        self.assertIsNotNone(decision["wait_activity"])
        self.assertNotEqual(decision["wait_activity"]["id"], "low_singing")
        self.assertFalse(decision["hum"]["selection"]["allow_singing"])

    def test_wait_entertainment_uses_plain_presence_for_serious_context(self) -> None:
        activity = wait_entertainment_for_context(
            13000,
            conversation_tone="serious_grief",
            user_mood="frustrated",
        )
        self.assertIsNotNone(activity)
        self.assertEqual(activity["id"], "plain_presence")
        self.assertEqual(activity["kind"], "chatterbox_voice")
        self.assertNotIn("playful", activity["mood_tags"])

    def test_eta_decision_answers_without_cancelling_existing_work(self) -> None:
        decision = wait_decision_for_expected_delay(9000, eta_requested=True)
        self.assertEqual(decision["text"], "Probably under ten seconds.")
        self.assertTrue(decision["should_speak"])
        self.assertFalse(decision["should_start_hum"])
        self.assertTrue(decision["keeps_existing_work_alive"])

    def test_cache_usage_manifest_covers_required_categories(self) -> None:
        usages = cache_usages()
        categories = {usage["category"] for usage in usages}
        self.assertEqual(
            categories,
            {
                "eta_response",
                "expected_wait_response",
                "hum_laughter_interstitial",
                "interruption_acknowledgement",
                "low_buffer_filler",
            },
        )
        self.assertEqual(
            sum(1 for usage in usages if usage["category"] == "interruption_acknowledgement"),
            len(INTERRUPTION_ACKNOWLEDGEMENTS),
        )
        self.assertEqual(
            sum(1 for usage in usages if usage["category"] == "low_buffer_filler"),
            len(LOW_BUFFER_FILLERS),
        )
        self.assertTrue(
            any(usage.get("hum_candidate") for usage in usages),
            "long wait cache should mark optional hum candidates",
        )
        self.assertTrue(
            all(
                usage.get("interrupt_policy") == "answer_eta_without_cancelling_work"
                for usage in usages
                if usage["category"] == "eta_response"
            )
        )
        self.assertEqual(
            sum(1 for usage in usages if usage["category"] == "hum_laughter_interstitial"),
            len(HUM_INTERSTITIALS),
        )
        self.assertTrue(
            all(
                usage.get("can_interrupt_hum") and usage.get("interrupt_policy") == "keeps_existing_work_alive"
                for usage in usages
                if usage["category"] == "hum_laughter_interstitial"
            )
        )

    def test_render_cache_entries_deduplicate_by_text_and_stage(self) -> None:
        usages = cache_usages()
        entries = render_cache_entries(usages, ref_audio="/data/embry_ref.wav")
        self.assertLess(len(entries), len(usages))
        self.assertTrue(all(entry["text_sha256"] == entry["render_material"]["text_sha256"] for entry in entries))
        self.assertTrue(all(entry["delivery_stage"] == "holding" for entry in entries))
        self.assertTrue(all(entry["render_material"]["ref_audio"] == "/data/embry_ref.wav" for entry in entries))

    def test_wait_and_eta_rules_have_non_overlapping_ordered_ranges(self) -> None:
        for rules in (WAIT_RESPONSE_RULES, ETA_RESPONSE_RULES):
            previous_max: int | None = None
            for rule in rules:
                self.assertGreaterEqual(rule["min_wait_ms"], 700)
                if previous_max is not None:
                    self.assertEqual(rule["min_wait_ms"], previous_max)
                previous_max = rule["max_wait_ms"]
            self.assertIsNone(rules[-1]["max_wait_ms"])


if __name__ == "__main__":
    unittest.main()
