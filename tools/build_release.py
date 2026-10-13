"""Build and package a clean desktop artifact without touching the live release."""
from __future__ import annotations
import argparse
import datetime as dt
import shutil
import subprocess
import sys
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_FILES = ("config.example.yaml", ".env.example", "README.md", "INSTRUCTION_RU.txt")

def package_artifact(source: Path, artifact_root: Path, exe_path: Path) -> Path:
    target = artifact_root / "LenormandGroupBot"
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(exe_path, target / "LenormandGroupBot.exe")
    for name in SAFE_FILES:
        path = source / name
        if path.is_file(): shutil.copy2(path, target / name)
    day = target / "cards" / "day"
    day.mkdir(parents=True)
    guide = source / "cards" / "day" / "README.md"
    if guide.is_file():
        shutil.copy2(guide, day / "README.md")
    else:
        (day / "README.md").write_text("Поместите сюда изображения карт дня JPG или PNG.\n", encoding="utf-8")
    return target

def build(source: Path, version: str | None = None, python: str | None = None) -> Path:
    source = source.resolve()
    version = version or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version) or version in {".", ".."}:
        raise ValueError("version must be a single safe path component")
    output_root = source / "outputs" / version
    work_root = source / ".cache" / "pyinstaller" / version
    work_root.mkdir(parents=True, exist_ok=False)
    dist_root, build_root = work_root / "dist", work_root / "build"
    venv_python = source / ".venv-build" / "Scripts" / "python.exe"
    cache = source / ".cache"
    temp = source / "work" / "tmp"
    cache.mkdir(exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"PIP_CACHE_DIR": str(cache / "pip"), "PYINSTALLER_CONFIG_DIR": str(cache / "pyinstaller-config"), "TEMP": str(temp), "TMP": str(temp), "PYTHONDONTWRITEBYTECODE": "1"})
    if not venv_python.exists():
        subprocess.run([python or sys.executable, "-m", "venv", str(source / ".venv-build")], cwd=source, env=env, check=True)
    subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(source / "requirements.txt"), "-r", str(source / "requirements-build.txt")], cwd=source, env=env, check=True)
    subprocess.run([str(venv_python), "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist_root), "--workpath", str(build_root), str(source / "LenormandGroupBot.spec")], cwd=source, env=env, check=True)
    return package_artifact(source, output_root, dist_root / "LenormandGroupBot.exe")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--version")
    parser.add_argument("--python")
    args = parser.parse_args()
    print(build(args.source, args.version, args.python))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
