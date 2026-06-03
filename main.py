from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.admin_panel import run_admin_panel
from app.bot import run_bot
from app.setup_wizard import run_setup_wizard


def needs_first_setup() -> bool:
    return not Path(".env").exists() or not Path("config.yaml").exists()


def use_exe_directory() -> None:
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).parent)


if __name__ == "__main__":
    use_exe_directory()

    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard.")
    parser.add_argument("--bot-only", action="store_true", help="Run only the Telegram bot process.")
    args = parser.parse_args()

    if args.bot_only:
        run_bot()
    elif args.setup or needs_first_setup():
        run_setup_wizard()
        run_admin_panel()
    else:
        run_admin_panel()
