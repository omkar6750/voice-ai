"""Create and inspect one Git worktree per unit of work."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKTREES = ROOT.parent / f"{ROOT.name}-worktrees"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def run(*args: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def start(slug: str) -> None:
    if not SLUG.fullmatch(slug):
        raise SystemExit("slug must be lowercase-hyphenated")
    target = WORKTREES / slug
    if target.exists():
        raise SystemExit(f"worktree exists: {target}")
    WORKTREES.mkdir(exist_ok=True)
    run("git", "worktree", "add", "-b", f"work/{slug}", str(target), "main")
    print(target)


def list_worktrees() -> None:
    print(run("git", "worktree", "list"))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("slug")
    sub.add_parser("list")
    args = parser.parse_args()
    if args.command == "start":
        start(args.slug)
    else:
        list_worktrees()


if __name__ == "__main__":
    main()
