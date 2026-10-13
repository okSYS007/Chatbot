import json
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from app.config import load_config, save_daily_card
from app.storage_json import JsonStorage, default_state
from tests.support import project_temp


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = project_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_existing_database_loaded_unchanged_and_new_settings_preserve_it(self):
        original = default_state()
        original.update({
            "users": {"1": {"reputation": 154, "welcomed": True, "custom": "keep"}},
            "counted_reactions": {"old": "not_admin_reaction", "new": {"weight": 1}},
            "rep_events": [{"author_id": 1, "weight": 154}],
            "settings": {"welcome_text": "Прод {name}", "custom": [1, 2]},
            "unknown_future_key": {"keep": True},
        })
        path = self.root / "state.json"
        path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        old_bytes = path.read_bytes()
        storage = JsonStorage(path)
        self.assertEqual(path.read_bytes(), old_bytes)
        storage.set_settings({"welcome_texts": ["Привет, {name}", "Рады видеть, {name}"]})
        after = json.loads(path.read_text(encoding="utf-8"))
        for key in original:
            if key != "settings":
                self.assertEqual(after[key], original[key])
        self.assertEqual(after["settings"]["custom"], [1, 2])
        self.assertEqual((self.root / "state.backup.json").read_bytes(), old_bytes)

    def test_legacy_missing_fields_migration_is_additive(self):
        original = {"users": {"9": {"reputation": 250}}, "settings": {"welcome_text": "old"}}
        path = self.root / "state.json"
        path.write_text(json.dumps(original), encoding="utf-8")
        storage = JsonStorage(path)
        self.assertEqual(storage.snapshot()["users"], original["users"])
        self.assertEqual(storage.snapshot()["settings"], original["settings"])
        self.assertEqual(json.loads((self.root / "state.backup.json").read_text()), original)

    def test_corrupt_database_fails_without_replacing_it(self):
        path = self.root / "state.json"
        path.write_bytes(b'{"users":')
        with self.assertRaises(json.JSONDecodeError):
            JsonStorage(path)
        self.assertEqual(path.read_bytes(), b'{"users":')
        self.assertFalse((self.root / "state.backup.json").exists())

    def test_old_config_loads_disabled_without_rewriting(self):
        path = self.root / "config.yaml"
        original = "welcome:\n  text: Old welcome\nstorage:\n  path: custom/state.json\n"
        path.write_text(original, encoding="utf-8")
        with patch("app.config.load_dotenv"), patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:fake"}):
            config = load_config(str(path))
        self.assertFalse(config.daily_card.enabled)
        self.assertEqual(config.daily_card.timezone, "Europe/Kyiv")
        self.assertEqual(config.storage.path, Path("custom/state.json"))
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_daily_settings_merge_preserves_all_existing_sections(self):
        original = {"storage": {"path": "original/database.json"}, "admins": {"user_ids": [1]}, "welcome": {"text": "old"}, "custom": {"x": 42}}
        path = self.root / "config.yaml"
        path.write_text(yaml.safe_dump(original), encoding="utf-8")
        save_daily_card({"time": "11:25", "timezone": "Europe/Kyiv", "chat_id": -1001, "enabled": True}, str(path))
        after = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, value in original.items():
            self.assertEqual(after[key], value)
        self.assertEqual(after["daily_card"]["time"], "11:25")

    def test_invalid_config_is_not_written(self):
        path = self.root / "config.yaml"
        path.write_text("custom: keep\n", encoding="utf-8")
        for values in [{"time": "24:00"}, {"time": "9:00"}, {"timezone": "Mars/Test"}, {"message_thread_id": -1}, {"enabled": True}, {"caption": "{name.__class__}"}, {"caption": "{}"}, {"enabled": "false"}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                save_daily_card(values, str(path))
        self.assertEqual(path.read_text(), "custom: keep\n")
