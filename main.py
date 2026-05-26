from __future__ import annotations

import argparse

from app.bot import run_bot
from app.setup_wizard import run_setup_wizard


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard.")
    args = parser.parse_args()

    if args.setup:
        run_setup_wizard()
    else:
        run_bot()
