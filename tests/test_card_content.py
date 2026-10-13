import io
import tempfile
import unittest
import zipfile
import os
from pathlib import Path

from app.card_content import read_card_text, scan_card_folder


DOC = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Привет</w:t><w:tab/><w:t>мир</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''


class CardContentTests(unittest.TestCase):
    def tempdir(self):
        base = Path(__file__).parents[1] / "work" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def test_scan_and_text_formats(self):
        with self.tempdir() as raw:
            root = Path(raw); (root / "images").mkdir(); (root / "texts").mkdir()
            (root / "images" / "b.PNG").write_bytes(b"x"); (root / "texts" / "a.txt").write_text("текст", encoding="utf-8")
            (root / "old.doc").write_bytes(b"x"); (root / "~$tmp.txt").write_text("x")
            found = scan_card_folder(root)
            self.assertEqual([p.name for p in found.images], ["b.PNG"])
            self.assertEqual([p.name for p in found.texts], ["a.txt"])
            self.assertEqual([p.name for p in found.unsupported_texts], ["old.doc"])
            self.assertEqual(read_card_text(root / "texts" / "a.txt"), "текст")

    def test_docx_paragraphs_tables_and_hidden(self):
        with self.tempdir() as raw:
            path = Path(raw) / "x.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", DOC)
            self.assertEqual(read_card_text(path), "Привет\tмир\nA\nB\tC")

    def test_txt_boms_empty_and_invalid(self):
        with self.tempdir() as raw:
            root = Path(raw)
            (root / "utf8.txt").write_bytes(b"\xef\xbb\xbfhello")
            (root / "utf16.txt").write_bytes("hello".encode("utf-16"))
            (root / "empty.txt").write_bytes(b" \n")
            (root / "bad.txt").write_bytes(b"\xff\xfe\xfa")
            self.assertEqual(read_card_text(root / "utf8.txt"), "hello")
            self.assertEqual(read_card_text(root / "utf16.txt"), "hello")
            with self.assertRaises(ValueError): read_card_text(root / "empty.txt")
            with self.assertRaises(ValueError): read_card_text(root / "bad.txt")

    def test_docx_hidden_deleted_runs_breaks_and_table_paragraphs(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>visible</w:t><w:br/><w:t>line</w:t><w:tab/><w:t>tab</w:t></w:r><w:r><w:rPr><w:vanish w:val="true"/></w:rPr><w:t>hidden</w:t></w:r><w:del><w:r><w:t>deleted</w:t></w:r></w:del><w:r><w:rPr><w:vanish w:val="false"/></w:rPr><w:t>shown</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>one</w:t></w:r></w:p><w:p><w:r><w:t>two</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>three</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>'''
        with self.tempdir() as raw:
            path = Path(raw) / "x.docx"
            with zipfile.ZipFile(path, "w") as archive: archive.writestr("word/document.xml", xml)
            self.assertEqual(read_card_text(path), "visible\nline\ttabshown\none\ntwo\tthree")

    def test_docx_rejection_cases_and_limits(self):
        with self.tempdir() as raw:
            root = Path(raw)
            bad = root / "bad.docx"; bad.write_bytes(b"no zip")
            missing = root / "missing.docx"
            with zipfile.ZipFile(missing, "w") as z: z.writestr("word/other.xml", "x")
            dtd = root / "dtd.docx"
            with zipfile.ZipFile(dtd, "w") as z: z.writestr("word/document.xml", "<!DOCTYPE x [<!ENTITY y 'x'>]><x>&y;</x>")
            large = root / "large.docx"
            with zipfile.ZipFile(large, "w") as z: z.writestr("word/document.xml", "x" * (4 * 1024 * 1024 + 1))
            for path in (bad, missing, dtd, large):
                with self.assertRaises(ValueError): read_card_text(path)

    def test_escape_symlink_is_ignored(self):
        with self.tempdir() as raw:
            sandbox = Path(raw)
            root = sandbox / "selected"
            root.mkdir()
            outside = sandbox / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self.assertEqual(scan_card_folder(root).texts, ())

    def test_bad_and_old_documents(self):
        with self.tempdir() as raw:
            root = Path(raw); bad = root / "bad.docx"; bad.write_bytes(b"no")
            with self.assertRaises(ValueError): read_card_text(bad)
            with self.assertRaisesRegex(ValueError, "устарел"): read_card_text(root / "x.doc")


if __name__ == "__main__":
    unittest.main()
