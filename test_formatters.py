#!/usr/bin/env python3
"""Offline tests for the answer formatters (via quickstart.py's copies).

    python3 test_formatters.py

The project's whole pitch is exactness, so the formatters get tests.
They run against `snapshot.example.json` — a real snapshot — with no
Switch stack, no secrets, and no network. The live service's formatters
are the same code (duplicated into quickstart.py so this demo can never
import the running service); `evidence/transcript.md` is the ground
truth for what the live agent actually said.
"""
import json
import unittest
from pathlib import Path

import quickstart

SNAPSHOT = json.loads((Path(__file__).parent / "snapshot.example.json").read_text())


class FormatterTests(unittest.TestCase):
    def test_all_seven_formatters_answer(self):
        self.assertEqual(set(quickstart.FORMATTERS),
                         {"deadlines", "gates", "money", "health", "brief", "status", "prs"})
        for kind, fn in quickstart.FORMATTERS.items():
            out = fn(SNAPSHOT)
            self.assertIsInstance(out, str, kind)
            self.assertGreater(len(out), 40, kind)

    def test_board_headline_matches_snapshot(self):
        out = quickstart.fmt_deadlines(SNAPSHOT)
        self.assertIn(f"{SNAPSHOT['deadlines']['active_total']} active items", out)

    def test_brief_carries_the_board_counts(self):
        out = quickstart.fmt_brief(SNAPSHOT)
        self.assertIn("Portfolio brief", out)
        self.assertIn(str(SNAPSHOT["prs"]["open"]), out)

    def test_money_names_real_amounts_from_the_register(self):
        out = quickstart.fmt_money(SNAPSHOT)
        amounts = [i["amount"] for i in SNAPSHOT["money"]["overdue"] if i.get("amount")]
        for amt in amounts:
            self.assertIn(amt, out)

    def test_health_reports_every_monitor(self):
        out = quickstart.fmt_health(SNAPSHOT)
        for m in SNAPSHOT["watch"]["monitors"]:
            self.assertIn(m["name"], out)
            self.assertIn(m["status"], out)

    def test_no_answer_invents_a_live_query(self):
        # The honesty rule: answers are snapshot-shaped, never query-shaped.
        for fn in quickstart.FORMATTERS.values():
            self.assertNotIn("live query", fn(SNAPSHOT).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
