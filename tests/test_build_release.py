import sys
import shutil
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from tools.build_release import package_artifact


class BuildReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (Path(__file__).parents[1] / "work" / "tmp").mkdir(parents=True, exist_ok=True)

    def test_existing_release_is_untouched_and_artifact_is_whitelisted(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / "work" / "tmp") as tmp:
            root = Path(tmp)
            live_db = root / "release" / "LenormandGroupBot" / "data" / "state.json"
            live_db.parent.mkdir(parents=True)
            live_db.write_text('{"users": {"1": {}}}', encoding="utf-8")
            for name in ("config.example.yaml", ".env.example", "README.md", "INSTRUCTION_RU.txt"):
                (root / name).write_text(name, encoding="utf-8")
            (root / "config.yaml").write_text("secret: must-not-ship", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
            exe = root / "built.exe"
            exe.write_bytes(b"exe")

            target = package_artifact(root, root / "outputs" / "test", exe)

            self.assertEqual(live_db.read_text(encoding="utf-8"), '{"users": {"1": {}}}')
            names = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
            self.assertIn("LenormandGroupBot.exe", names)
            self.assertIn("cards/day/README.md", names)
            self.assertNotIn("config.yaml", names)
            self.assertNotIn(".env", names)
            self.assertNotIn("data/state.json", names)

    def test_version_rejects_path_traversal(self):
        from tools.build_release import build
        with self.assertRaises(ValueError):
            build(Path(__file__).parents[1], "../escape")

    def test_failed_pyinstaller_does_not_touch_release(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / "work" / "tmp") as tmp:
            root = Path(tmp)
            live = root / "release" / "LenormandGroupBot" / "data" / "state.json"
            live.parent.mkdir(parents=True)
            live.write_text("live", encoding="utf-8")
            from tools import build_release
            original = build_release.subprocess.run
            def fail(*args, **kwargs):
                raise RuntimeError("synthetic failure")
            build_release.subprocess.run = fail
            try:
                with self.assertRaises(RuntimeError):
                    build_release.build(root, "test")
            finally:
                build_release.subprocess.run = original
            self.assertEqual(live.read_text(encoding="utf-8"), "live")


if __name__ == "__main__":
    unittest.main()
