import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.storage_json import JsonStorage
from app.welcome import (
    get_welcome_text,
    get_welcome_templates,
    render_welcome,
    validate_welcome_template,
    validate_welcome_templates,
)


class WelcomeTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(__file__).resolve().parents[1] / "work" / "tmp"
        self.work.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.work)
        self.storage = JsonStorage(Path(self.tmp.name) / "state.json")
        self.config = SimpleNamespace(welcome=SimpleNamespace(text="fallback", texts=("one", "two")))

    def tearDown(self):
        self.tmp.cleanup()

    def test_template_validation(self):
        self.assertIsNone(validate_welcome_template("Привет, {name}!"))
        self.assertIn("Неизвестные", validate_welcome_template("{bad}"))
        self.assertIsNotNone(validate_welcome_template("{"))
        self.assertIsNotNone(validate_welcome_template("x" * 4097))
        self.assertIsNotNone(validate_welcome_template("😀" * 2049))
        self.assertIsNone(validate_welcome_template("{{name}}"))

    def test_saved_list_has_priority_and_legacy_is_compatible(self):
        self.assertEqual(get_welcome_templates(self.config, self.storage), ["one", "two"])
        self.storage.state["settings"] = {"welcome_text": "legacy"}
        self.storage.save()
        self.assertEqual(get_welcome_templates(self.config, self.storage), ["legacy"])
        self.storage.state["settings"]["welcome_texts"] = ["a", "b"]
        self.storage.save()
        self.assertEqual(get_welcome_templates(self.config, self.storage), ["a", "b"])

    def test_validation_list_rejects_empty_item(self):
        values, error = validate_welcome_templates(["a", ""])
        self.assertEqual(values, [])
        self.assertIsNotNone(error)

    def test_render(self):
        user = SimpleNamespace(full_name="Ира", username="ira", id=7)
        chat = SimpleNamespace(title="Таро")
        self.assertEqual(render_welcome("{name} {username} {user_id} {group}", user, chat), "Ира @ira 7 Таро")
        rendered = render_welcome("😀" * 5000, user, chat)
        self.assertLessEqual(len(rendered.encode("utf-16-le")), 8192)

    def test_random_choice_is_used(self):
        self.storage.state["settings"] = {"welcome_texts": ["a", "b"]}
        self.storage.save()
        with patch("app.welcome.random.choice", return_value="b") as choice:
            self.assertEqual(get_welcome_text(self.config, self.storage), "b")
            choice.assert_called_once_with(["a", "b"])

    def test_render_invalid_template_uses_fallback(self):
        user = SimpleNamespace(full_name="Ира", username=None, id=7)
        chat = SimpleNamespace(title="Таро")
        self.assertEqual(render_welcome("{name.__class__}", user, chat), "Привет, Ира! Добро пожаловать в группу.")

    def test_admin_commands_denied_without_write(self):
        from app.handlers.admin import set_welcomes
        update = SimpleNamespace(effective_user=SimpleNamespace(id=99), effective_message=SimpleNamespace(reply_text=AsyncMock()))
        storage = SimpleNamespace(set_settings=unittest.mock.Mock())
        config = SimpleNamespace(admins=SimpleNamespace(user_ids={1}))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"storage": storage, "config": config}))
        import asyncio
        asyncio.run(set_welcomes(update, context))
        storage.set_settings.assert_not_called()
        update.effective_message.reply_text.assert_not_awaited()


class AdminWelcomeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {"users": {"7": {"reputation": 12}}, "rep_events": [{"weight": 1}], "settings": {"keep": "yes", "welcome_texts": ["old"]}}
        self.storage = SimpleNamespace(
            state=self.state,
            set_settings=self._set_settings,
            snapshot=lambda: self.state,
        )
        self.message = SimpleNamespace(reply_text=AsyncMock())
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=self.message)
        self.config = SimpleNamespace(admins=SimpleNamespace(user_ids={1}))
        self.context = SimpleNamespace(
            args=[], application=SimpleNamespace(bot_data={"storage": self.storage, "config": self.config})
        )

    def _set_settings(self, values):
        self.state["settings"].update(values)

    async def test_authorized_set_welcomes_saves_all_variants(self):
        from app.handlers.admin import set_welcomes
        self.context.args = ["Привет,", "{name}!", "|", "Рады видеть,", "{username}!"]
        await set_welcomes(self.update, self.context)
        self.assertEqual(self.state["settings"]["welcome_texts"], ["Привет, {name}!", "Рады видеть, {username}!"])
        self.message.reply_text.assert_awaited_once()

    async def test_invalid_unknown_placeholder_does_not_write(self):
        from app.handlers.admin import set_welcomes
        self.context.args = ["Привет,", "{unknown}!", "|", "ok"]
        before = dict(self.state["settings"])
        await set_welcomes(self.update, self.context)
        self.assertEqual(self.state["settings"], before)
        self.message.reply_text.assert_awaited_once()

    async def test_set_welcome_clears_list_and_preserves_state(self):
        from app.handlers.admin import set_welcome
        self.context.args = ["Одиночное", "{name}! "]
        await set_welcome(self.update, self.context)
        self.assertEqual(self.state["settings"]["welcome_text"], "Одиночное {name}!")
        self.assertEqual(self.state["settings"]["welcome_texts"], [])
        self.assertEqual(self.state["settings"]["keep"], "yes")
        self.assertIn("7", self.state["users"])
        self.assertEqual(self.state["rep_events"], [{"weight": 1}])


if __name__ == "__main__":
    unittest.main()
