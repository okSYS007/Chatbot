import unittest
from pathlib import Path

import yaml

from app.config import parse_daily_card, save_daily_card
from tests.support import project_temp


class DailyCardFolderConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = project_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_new_folder_mode_round_trip_preserves_other_sections(self):
        path = self.root / "config.yaml"
        original = {"telegram": {"chat_id": 7}, "storage": {"path": "prod/state.json"}, "custom": {"keep": True}}
        path.write_text(yaml.safe_dump(original), encoding="utf-8")
        config = save_daily_card({
            "enabled": True, "chat_id": -100, "time": "08:30",
            "images_folder": "cards/Картинки", "texts_folder": "cards/Текст",
            "patterns": ["8 пентаклей", "10 кубков"],
        }, str(path))
        self.assertTrue(config.uses_patterns)
        self.assertEqual(config.images_folder, Path("cards/Картинки"))
        self.assertEqual(config.patterns, ("8 пентаклей", "10 кубков"))
        saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["storage"], original["storage"])
        self.assertEqual(saved["custom"], original["custom"])
        self.assertEqual(saved["daily_card"]["patterns"], ["8 пентаклей", "10 кубков"])

    def test_new_mode_defaults_folders_when_section_mentions_patterns(self):
        config = parse_daily_card({"patterns": ["8 пентаклей"]})
        self.assertEqual(config.images_folder, Path("cards/images"))
        self.assertEqual(config.texts_folder, Path("cards/texts"))
        self.assertFalse(config.enabled)

    def test_disabled_new_mode_can_have_no_patterns(self):
        config = parse_daily_card({"enabled": False, "images_folder": "i", "texts_folder": "t", "patterns": []})
        self.assertEqual(config.patterns, ())

    def test_enabled_new_mode_requires_pattern(self):
        with self.assertRaises(ValueError):
            parse_daily_card({"enabled": True, "chat_id": -1, "images_folder": "i", "texts_folder": "t", "patterns": []})

    def test_patterns_must_be_list_and_paths_must_be_nonempty_strings(self):
        cases = [
            {"patterns": ("8 пентаклей",)},
            {"patterns": [None]},
            {"images_folder": None},
            {"texts_folder": ""},
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_daily_card(raw)

    def test_patterns_are_normalized_and_duplicates_rejected(self):
        config = parse_daily_card({"patterns": ["  8   ПЕНТАКЛЕЙ "]})
        self.assertEqual(config.patterns, ("8 пентаклей",))
        with self.assertRaises(ValueError):
            parse_daily_card({"patterns": ["8 пентаклей", " 8_пентаклей "]})

    def test_legacy_mode_remains_unchanged(self):
        config = parse_daily_card({"folder": "cards/day", "caption": "Карта: {name}"})
        self.assertFalse(config.uses_patterns)
        self.assertIsNone(config.images_folder)
        self.assertIsNone(config.texts_folder)
        self.assertEqual(config.folder, Path("cards/day"))


if __name__ == "__main__":
    unittest.main()
