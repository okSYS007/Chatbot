from __future__ import annotations

import argparse
from pathlib import Path

from app.bot import run_bot
from app.setup_wizard import run_setup_wizard


def needs_first_setup() -> bool:
    return not Path(".env").exists() or not Path("config.yaml").exists()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard.")
    args = parser.parse_args()

    if args.setup or needs_first_setup():
        run_setup_wizard()
    else:
        run_bot()
