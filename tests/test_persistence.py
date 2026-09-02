import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class FakeApp:
    def __init__(self):
        self.tasks = [{"id": "1", "title": "Test", "start": "2026-09-02T12:00:00",
                       "duration": 30, "repeat": ""}]
        self.stream_settings = {"platform": "YouTube"}
        self.warnings = []

    def after(self, _delay, callback):
        self.warnings.append(callback)


class PersistenceTests(unittest.TestCase):
    def test_atomic_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "schedule.json"
            fake = FakeApp()
            with patch("app.data_file", return_value=destination):
                app.ScheduleBot.save(fake)
                tasks, settings = app.ScheduleBot.load_data(fake)
            self.assertEqual(tasks, fake.tasks)
            self.assertEqual(settings, fake.stream_settings)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_invalid_data_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "schedule.json"
            destination.write_text("not json", encoding="utf-8")
            fake = FakeApp()
            with patch("app.data_file", return_value=destination):
                tasks, settings = app.ScheduleBot.load_data(fake)
            self.assertEqual((tasks, settings), ([], {}))
            self.assertFalse(destination.exists())
            self.assertEqual((Path(directory) / "schedule.invalid.json").read_text(), "not json")
            self.assertEqual(len(fake.warnings), 1)

    def test_legacy_list_format_still_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "schedule.json"
            destination.write_text(json.dumps([{"id": "legacy"}]), encoding="utf-8")
            fake = FakeApp()
            with patch("app.data_file", return_value=destination):
                tasks, settings = app.ScheduleBot.load_data(fake)
            self.assertEqual(tasks, [{"id": "legacy"}])
            self.assertEqual(settings, {})


if __name__ == "__main__":
    unittest.main()
