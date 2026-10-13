import unittest

from app.message_parts import split_telegram_text


class MessagePartsTests(unittest.TestCase):
    def assert_valid(self, text, limit=4096):
        parts = split_telegram_text(text, limit)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= limit for part in parts))
        self.assertTrue(all(part.strip() for part in parts))

    def test_long_cyrillic_and_emoji(self):
        self.assert_valid(("Привет 😀 " * 700).strip())

    def test_exact_limit(self):
        self.assertEqual(split_telegram_text("a" * 4096), ["a" * 4096])

    def test_prefers_paragraph_and_preserves_text(self):
        text = "Абзац один.\n\nАбзац два.\nПродолжение. " * 500
        self.assert_valid(text)
        self.assertTrue(any("\n\n" in part for part in split_telegram_text(text)))

    def test_paragraph_boundary_has_priority_over_later_space(self):
        text = "a" * 10 + "\n\n" + "b" * 5 + " " + "c" * 20
        parts = split_telegram_text(text, 25)
        self.assertEqual("".join(parts), text)
        self.assertEqual(parts[0], "a" * 10 + "\n\n")

    def test_trailing_newline_is_kept_without_whitespace_chunk(self):
        text = "a" * 4096 + "\n"
        parts = split_telegram_text(text)
        self.assertEqual("".join(parts), text)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[-1].endswith("\n"))

    def test_trailing_whitespace_regressions(self):
        for text in ("a" * 4095 + "\n\n", "a" * 4090 + " " * 10):
            self.assert_valid(text)
        with self.assertRaises(ValueError):
            split_telegram_text("a\n", 1)

    def test_huge_word(self):
        self.assert_valid("x" * 10000, 100)

    def test_emoji_boundary(self):
        self.assert_valid("a" * 4094 + "😀", 4096)
        with self.assertRaises(ValueError):
            split_telegram_text("😀", 1)

    def test_whitespace_shape_and_empty(self):
        text = "слово   слово\n\nслово"
        self.assert_valid(text, 8)
        self.assertEqual(split_telegram_text(""), [])
        with self.assertRaises(ValueError):
            split_telegram_text("   ")


if __name__ == "__main__":
    unittest.main()
