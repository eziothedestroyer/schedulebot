import re
import unittest
from pathlib import Path

from version import VERSION


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_installer_version_matches_application(self):
        text = (ROOT / "version.nsh").read_text(encoding="utf-8")
        match = re.search(r'APP_VERSION\s+"([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), VERSION)

    def test_private_material_is_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("private/", ignored)
        self.assertIn("schedule.json", ignored)
        self.assertIn(".env", ignored)


if __name__ == "__main__":
    unittest.main()
