"""Entry point: `python -m shiguang` or `shiguang` / `shi` command."""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="shiguang",
        description="拾光 · AfterGlow — TUI reflective journal",
    )
    parser.add_argument(
        "--folder", "-f",
        help="Path to diary folder (default: ~/Documents/Journal or $SHIGUANG_FOLDER)",
    )
    parser.add_argument(
        "--version", "-V", action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "--sanity-check", action="store_true",
        help="Run a non-TUI sanity check on the diary folder and exit",
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize the diary folder with a sample entry and exit",
    )
    parser.add_argument(
        "folder_pos", nargs="?",
        help="(positional) Folder for --init/--sanity-check",
    )

    args = parser.parse_args()

    # Folder resolution: --folder > positional > state > default
    folder = args.folder or args.folder_pos or None

    if args.version:
        from shiguang import __version__
        print(f"shiguang {__version__}")
        return 0

    if args.sanity_check:
        from shiguang.sanity import run_sanity_check
        return run_sanity_check(folder)

    if args.init:
        from shiguang.init_cmd import run_init
        return run_init(folder)

    # Default: launch TUI
    from shiguang.app import ShiGuangApp
    app = ShiGuangApp(folder=folder)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
