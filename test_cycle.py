import asyncio
import json
import unittest
from datetime import date
from unittest.mock import patch

import cycle


class PhaseTests(unittest.TestCase):
    def test_recorded_end_and_phase_boundaries(self):
        periods = [{"start_date": "2026-08-21", "end_date": "2026-08-26"}]
        for today, expected in [
            ("2026-08-21", "menstrual"),
            ("2026-08-26", "menstrual"),
            ("2026-08-27", "follicular"),
            ("2026-09-03", "follicular"),  # 15 days left
            ("2026-09-04", "ovulation"),  # 14 days left
            ("2026-09-10", "ovulation"),  # 8 days left
            ("2026-09-11", "luteal"),     # 7 days left
            ("2026-09-19", "luteal"),
        ]:
            with self.subTest(today=today):
                self.assertEqual(cycle.current_phase(periods, date.fromisoformat(today))["phase"], expected)

    def test_early_end_overrides_estimate(self):
        periods = [{"start_date": "2026-08-21", "end_date": "2026-08-22"}]
        self.assertEqual(cycle.current_phase(periods, date(2026, 8, 23))["phase"], "follicular")

    def test_missing_end_keeps_estimate(self):
        for end in (None, ""):
            self.assertEqual(cycle.current_phase(
                [{"start_date": "2026-08-21", "end_date": end}], date(2026, 8, 23)
            )["phase"], "menstrual")
        self.assertEqual(cycle.current_phase([])["phase"], "unknown")

    def test_status_requested_example(self):
        import selene_server

        periods = [{"start_date": "2026-08-21", "end_date": "2026-08-26"}]
        with patch("cycle.date") as clock, \
                patch.object(selene_server.db, "get_periods", return_value=periods), \
                patch.object(selene_server.db, "get_config", return_value=""):
            clock.today.return_value = date(2026, 9, 11)
            clock.fromisoformat.side_effect = date.fromisoformat
            result = json.loads(asyncio.run(selene_server.selene_status()))
        self.assertEqual(result["phase"], "luteal")
        self.assertEqual(result["days_left"], 7)
        self.assertEqual(result["next_date"], "2026-09-18")


if __name__ == "__main__":
    unittest.main()
