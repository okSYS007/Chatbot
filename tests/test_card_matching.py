import unittest
from pathlib import Path

from app.card_matching import (
    build_match_catalog,
    match_pattern,
    normalize_pattern,
    validate_patterns,
)


class CardMatchingTests(unittest.TestCase):
    def test_normalization_handles_case_spaces_and_underscores(self):
        self.assertEqual(normalize_pattern("  8__ПЕНТАКЛЕЙ\t"), "8 пентаклей")
        self.assertEqual(validate_patterns([" 8  пентаклей "]), ("8 пентаклей",))

    def test_validation(self):
        self.assertEqual(validate_patterns([]), ())
        with self.assertRaises(ValueError):
            validate_patterns([""])
        with self.assertRaises(ValueError):
            validate_patterns(["x", " X "])
        with self.assertRaises(ValueError):
            validate_patterns(["x" * 101])
        with self.assertRaises(ValueError):
            validate_patterns(["x"] * 201)

    def test_boundaries_and_literal_matching(self):
        patterns = ("8 пентаклей",)
        self.assertEqual(match_pattern("8 пентаклей часть души", patterns), "8 пентаклей")
        self.assertIsNone(match_pattern("18 пентаклей", patterns))
        self.assertIsNone(match_pattern("8 пентаклейник", patterns))
        self.assertEqual(match_pattern("8 [пентаклей]", ("[пентаклей]",)), "[пентаклей]")
        # Boundary checks apply only when the phrase edge itself is a word
        # character; punctuation in a literal phrase must remain matchable.
        self.assertEqual(match_pattern("x[пентаклей]y", ("[пентаклей]",)), "[пентаклей]")

    def test_nested_uses_most_specific_and_unrelated_is_ambiguous(self):
        self.assertEqual(match_pattern("8 пентаклей часть", ("пентаклей", "8 пентаклей")), "8 пентаклей")
        with self.assertRaises(ValueError):
            match_pattern("8 пентаклей", ("8", "пентаклей"))

    def test_catalog_groups_all_text_variants_by_image_stem(self):
        images = [Path("images/8 пентаклей часть души.jpg"), Path("images/10 кубков.jpg")]
        texts = [Path("texts/8 пентаклей средина моря.docx"), Path("texts/8__ПЕНТАКЛЕЙ второй.txt"), Path("texts/other.txt")]
        catalog = build_match_catalog(images, texts, ("8 пентаклей", "10 кубков"))
        self.assertEqual(len(catalog.pairs), 1)
        self.assertEqual(catalog.pairs[0].pattern, "8 пентаклей")
        self.assertEqual(len(catalog.pairs[0].texts), 2)
        self.assertEqual(catalog.missing_text_images, (Path("images/10 кубков.jpg"),))
        self.assertEqual(catalog.unmatched_texts, (Path("texts/other.txt"),))

    def test_ambiguous_and_unmatched_are_reported(self):
        catalog = build_match_catalog(
            [Path("18 пентаклей.jpg"), Path("8 пентаклей кубки.jpg"), Path("plain.jpg")],
            [Path("8 пентаклей.txt")],
            ("8 пентаклей", "кубки"),
        )
        self.assertEqual(catalog.unmatched_images, (Path("18 пентаклей.jpg"), Path("plain.jpg")))
        self.assertEqual(catalog.ambiguous_images, (Path("8 пентаклей кубки.jpg"),))

    def test_matching_uses_filename_stem_not_parent_folder(self):
        catalog = build_match_catalog(
            [Path("8 пентаклей/image.jpg")],
            [Path("8 пентаклей/text.txt")],
            ("8 пентаклей",),
        )
        self.assertEqual(catalog.unmatched_images, (Path("8 пентаклей/image.jpg"),))
        self.assertEqual(catalog.unmatched_texts, (Path("8 пентаклей/text.txt"),))


if __name__ == "__main__":
    unittest.main()
