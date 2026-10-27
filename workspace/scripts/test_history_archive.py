import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import live_data as data
import closing_archive as archive


class HistoryArchiveTests(unittest.TestCase):
    def test_html_is_standalone_and_frozen(self):
        snapshot = {"server_time": "2026-10-27T15:00:02+08:00", "market_session": {"phase": "trading", "expected_date": "2026-10-27"}, "sections": {}}
        with tempfile.TemporaryDirectory(dir=data.CACHE) as folder:
            path = archive.freeze_dashboard(snapshot, folder)
            content = path.read_text(encoding="utf-8")
            self.assertIn('globalThis.INDUSTRY_LIVE_MODE=false', content)
            self.assertNotIn('<script src=', content)
            self.assertNotIn('/assets/live-client.js', content)
            self.assertIn('2026-10-27T15:00:02+08:00', content)
            snapshot['server_time'] = '2026-10-27T16:30:00+08:00'
            archive.freeze_dashboard(snapshot, folder)
            self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_html_does_not_freeze_lunch_or_weekend(self):
        for captured in ('2026-10-27T12:00:00+08:00', '2026-10-28T16:00:00+08:00'):
            self.assertIsNone(archive.freeze_dashboard({'server_time': captured, 'market_session': {'expected_date': '2026-10-27'}}))

    def test_failed_history_keeps_cache(self):
        with tempfile.TemporaryDirectory(dir=data.CACHE) as folder, patch.object(data, "CACHE", Path(folder)), patch.object(data, "get", side_effect=ConnectionError):
            rows = [{"date": "2026-10-23", "pct_change": 1, "main_net_inflow_yi": 2}]
            data.atomic_json(Path(folder) / "BK1000-daily.json", rows)
            with patch.object(data.time, "time", return_value=99999999999):
                self.assertEqual(data.fetch_board_history("BK1000"), rows)

    def test_partial_response_does_not_erase_good_fields(self):
        old = [{"date": "2026-10-23", "pct_change": 1, "main_net_inflow_yi": 2}]
        newer = [{"date": "2026-10-23", "pct_change": 3, "main_net_inflow_yi": None}]
        self.assertEqual(data.merge_history(old, newer)[0], {"date": "2026-10-23", "pct_change": 3, "main_net_inflow_yi": 2})

    def test_history_repair_retains_quote_timestamp(self):
        section = {"status": "stale", "as_of": "2026-10-27T12:20:00+08:00", "data": {"items": [{"id": "BK1000", "days": []}]}}
        with patch.object(data, "fetch_board_history", return_value=[{"date": "2026-10-23", "pct_change": 1, "main_net_inflow_yi": 2}]):
            data.repair_concept_history(section)
        self.assertEqual(section["as_of"], "2026-10-27T12:20:00+08:00")
        self.assertEqual(len(section["data"]["items"][0]["days"]), 1)

    def test_archive_rejects_lunch_and_preserves_good_close(self):
        snapshot = {"market_session": {"phase": "closed_today", "expected_date": "2026-10-27"}, "sections": {"breadth": {"as_of": "2026-10-27T11:30:00+08:00", "data": {"up": 100}}}}
        with tempfile.TemporaryDirectory(dir=data.CACHE) as folder:
            first = archive.save_close(snapshot, folder)
            self.assertNotIn("breadth", first["sections"])
            snapshot["sections"]["breadth"]["as_of"] = "2026-10-27T15:00:00+08:00"
            archive.save_close(snapshot, folder)
            snapshot["sections"]["breadth"]["as_of"] = "2026-10-26T15:00:00+08:00"
            last = archive.save_close(snapshot, folder)
            self.assertEqual(last["sections"]["breadth"]["as_of"], "2026-10-27T15:00:00+08:00")
            self.assertEqual(last["status"], "partial")

    def test_does_not_archive_during_session(self):
        self.assertIsNone(archive.save_close({"market_session": {"phase": "lunch", "expected_date": "2026-10-27"}}))

    def test_board_quote_must_also_be_close(self):
        board = {"as_of": "2026-10-27T15:00:00+08:00", "quote_as_of": "2026-10-27T12:20:00+08:00", "pct": 1, "latest": dict.fromkeys(["main", "xl", "lg", "md", "sm"], 1)}
        section = {"as_of": board["as_of"], "data": {"items": [board] * 10}}
        self.assertFalse(archive.valid_section("concepts", section, "2026-10-27"))


if __name__ == "__main__":
    unittest.main()
