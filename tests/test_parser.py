import unittest
from datetime import datetime

from schedule_parser import parse_request


class ParserTests(unittest.TestCase):
    NOW = datetime(2026, 9, 1, 12, 0)  # Tuesday

    def test_tomorrow_and_duration(self):
        task = parse_request("Study tomorrow at 7 pm for 2 hours", self.NOW)
        self.assertEqual(task.title, "Study")
        self.assertEqual(task.start, datetime(2026, 9, 2, 19, 0))
        self.assertEqual(task.duration_minutes, 120)

    def test_weekly(self):
        task = parse_request("Gym every Monday at 6:30 am", self.NOW)
        self.assertEqual(task.start, datetime(2026, 9, 7, 6, 30))
        self.assertEqual(task.repeat, "weekly")

    def test_named_date(self):
        task = parse_request("Dentist September 5 at 2:30 pm", self.NOW)
        self.assertEqual(task.start, datetime(2026, 9, 5, 14, 30))


if __name__ == "__main__":
    unittest.main()

