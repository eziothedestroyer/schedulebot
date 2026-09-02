import json
import unittest

import ai_vod


class AiVodTests(unittest.TestCase):
    def test_extracts_and_limits_highlights(self):
        response = "result:\n" + json.dumps([
            {"start": "00:00:01", "end": "00:00:20", "title": "A" * 120,
             "reason": "B" * 220},
            {"start": "00:01:00", "end": "00:01:30", "title": "Second"},
        ])
        highlights = ai_vod._json_from_text(response)
        self.assertEqual(len(highlights), 2)
        self.assertEqual(len(highlights[0]["title"]), 100)
        self.assertEqual(len(highlights[0]["reason"]), 200)

    def test_rejects_non_list_json(self):
        with self.assertRaises(ValueError):
            ai_vod._json_from_text('{"title": "not a list"}')

    def test_rejects_blank_transcript(self):
        with self.assertRaises(ValueError):
            ai_vod._prompt("  ")


if __name__ == "__main__":
    unittest.main()
