#!/usr/bin/env python3
"""Unit tests for the Producer Agent v2 — run anywhere, no network.

    python3 -m unittest test_producer -v

Covers the three things that must never regress:
  * intent routing (every advertised intent routes; v2 intents win
    over broader v1 keywords),
  * truthfulness invariants in the formatters (credits numbers, the
    review gate, never-posted / earned $0),
  * the snapshot fallback chain (fresh -> last-good -> unavailable),
  * the room-document renderers (they carry the snapshot timestamp).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import producer_agent as pa
import room_documents as rd

SNAP = json.loads((Path(__file__).parent / "producer-snapshot.json").read_text())
CTX = {"origin": "fresh", "generated_at": SNAP["generated_at_toronto"],
       "age_minutes": 1.0,
       "docs": {"enabled": True, "documents": 2, "last_sync_toronto": "now",
                "last_change_toronto": "now", "last_error": None,
                "visibility": "room", "logged_in": True}}


class Routing(unittest.TestCase):
    def test_every_advertised_intent_routes(self):
        for name in ["status", "ideas", "script", "renders", "clips",
                     "credits", "review", "sources", "next", "health", "help"]:
            self.assertEqual(pa.intent(f"@producer {name}"), name, name)

    def test_v2_intents_win_over_broader_keywords(self):
        # "review" must not fall through to renders/clips keywords.
        self.assertEqual(pa.intent("what is the review gate for publishing?"), "review")
        self.assertEqual(pa.intent("how many credits are left?"), "credits")
        self.assertEqual(pa.intent("where does this data come from — sources?"), "sources")

    def test_unrelated_message_is_not_a_question(self):
        self.assertIsNone(pa.intent("good morning everyone"))


class Truthfulness(unittest.TestCase):
    def test_credits_numbers(self):
        out = pa.fmt_credits(SNAP, CTX)
        self.assertIn("2 of 150", out)
        self.assertIn("28", out)
        self.assertIn("PENDING", out)

    def test_review_gate(self):
        out = pa.fmt_review(SNAP, CTX)
        self.assertIn("NO — never posted", out)
        self.assertIn("$0", out)

    def test_clips_never_posted(self):
        out = pa.fmt_clips(SNAP, CTX)
        self.assertIn("NO — never posted", out)
        self.assertIn("$0", out)

    def test_status_reports_documents(self):
        out = pa.fmt_status(SNAP, CTX)
        self.assertIn("Room documents: 2 published", out)

    def test_every_answer_is_labelled(self):
        pa.STORE = pa.SnapshotStore()  # reads the repo snapshot next to the code
        out = pa.answer("status")
        self.assertIn("— Producer Agent · snapshot", out)


class FallbackChain(unittest.TestCase):
    def test_fresh_then_last_good_then_none(self):
        with tempfile.TemporaryDirectory() as d:
            fresh, cache = Path(d) / "s.json", Path(d) / "s.last-good.json"
            store = pa.SnapshotStore(fresh, cache)
            self.assertIsNone(store.load())               # nothing anywhere
            fresh.write_text(json.dumps(SNAP))
            view = store.load()
            self.assertEqual(view["origin"], "fresh")     # fresh wins
            self.assertTrue(cache.exists())               # cache warmed
            fresh.write_text("{ corrupt")
            view = store.load()
            self.assertEqual(view["origin"], "last-good cache")  # falls back
            cache.unlink()
            self.assertIsNone(store.load())               # honest unavailable


class Documents(unittest.TestCase):
    def test_renderers_carry_timestamp_and_truths(self):
        snap_doc = rd.render_snapshot_document(SNAP)
        self.assertIn(SNAP["generated_at_toronto"], snap_doc)
        self.assertIn("BLOCKED", snap_doc)
        state_doc = rd.render_state_document(SNAP)
        self.assertIn("never posted", state_doc)
        self.assertIn("Human review required", state_doc)


if __name__ == "__main__":
    unittest.main()
