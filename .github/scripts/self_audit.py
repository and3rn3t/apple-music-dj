#!/usr/bin/env python3
"""Pre-publish self-audit: run before tagging a release.

ClawHub's reviewer reads only the published package, and its verdict once flipped on identical code,
so remove anything it could plausibly flag *before* publishing instead of after.

  1. Runs the deterministic checks (trust claims, listing, packaging).
  2. Shows what changed in the shipped files since the last tag.
  3. Prints a review prompt that mimics the reviewer's concerns. Give it, with the diff, to a model
     or a person. That step is manual on purpose: CI holds no model key.

Usage:
  python3 .github/scripts/self_audit.py                   # checks, shipped changes since the last tag, prompt
  python3 .github/scripts/self_audit.py --since v3.3.0 --full    # embed the full diff in the prompt
  python3 .github/scripts/self_audit.py --no-tests        # skip step 1
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKS = ["tests/test_trust_claims.py", "tests/test_listing.py", "tests/test_packaging.py"]

CONCERNS = """\
You are reviewing a skill package before it is published to a registry whose automated reviewer
reads only the shipped files. Find anything that reviewer could reasonably flag. Check:

1. Undisclosed writes: any command that changes the user's account (create, add, remove, rate,
   favorite, schedule) without a preview and an explicit flag, or not listed in SKILL.md's
   "Data written" table.
2. Unattended actions: anything that runs without the user present (cron, background jobs) and
   writes, and whether installing it needs an explicit, reviewable confirmation.
3. Credentials: tokens in argv, logs, files, URLs or error messages; files holding secrets that are
   not owner-only; secrets echoed back to the user or the agent.
4. Network: any host besides the documented ones; any redirect, download-and-run, or install step.
5. Injection: user- or API-supplied text (artist names, playlist names, track titles) reaching a
   shell, a file path, JSON built by string concatenation, or an unquoted variable.
6. Prompt injection: text returned by the API or read from files that SKILL.md lets the agent treat
   as instructions instead of data.
7. Scope: filesystem access outside ~/.apple-music-dj/ and user-chosen output paths.
8. Mismatch: SKILL.md, README.md and clawhub.json claims (requirements, permissions, safety
   language) that the code does not back up, or code behavior the docs never mention.

Report each finding as: file:line, what a reviewer would say, severity (high/medium/low), and the
smallest fix. If a category is clean, say so in one line. Do not invent findings."""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def shipped_files() -> list[str]:
    """The files `clawhub publish` would upload (one definition, shared with tests/test_packaging.py)."""
    spec = importlib.util.spec_from_file_location("test_packaging", ROOT / "tests" / "test_packaging.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.shipped_files(ROOT)


def last_tag() -> str | None:
    try:
        return _git("describe", "--tags", "--abbrev=0").strip() or None
    except subprocess.CalledProcessError:
        return None


def shipped_changes(since: str, full: bool = False) -> str:
    files = shipped_files()
    args = ["diff", since if full else "--stat", *(["--"] if full else [since, "--"]), *files]
    return _git(*args).strip()


def review_prompt(since: str | None, changes: str) -> str:
    where = f"since {since}" if since else "(no earlier tag to compare with)"
    return f"{CONCERNS}\n\n--- Shipped files changed {where} ---\n{changes or '(none)'}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", help="compare with this tag or commit (default: the latest tag)")
    parser.add_argument("--full", action="store_true", help="embed the full diff, not just the file list")
    parser.add_argument("--no-tests", action="store_true")
    args = parser.parse_args(argv)

    status = 0
    if not args.no_tests:
        print("== 1. Deterministic checks ==", flush=True)
        status = subprocess.run([sys.executable, "-m", "pytest", "-q", *CHECKS], cwd=ROOT).returncode
        print("PASS" if status == 0 else "FAIL — fix these before publishing", "\n")

    since = args.since or last_tag()
    print(f"== 2. Shipped files changed since {since or 'the start'} ==")
    changes = shipped_changes(since, args.full) if since else "\n".join(shipped_files())
    print(changes or "(nothing in the published package changed)", "\n")

    print("== 3. Review prompt (give this to a model or a reviewer) ==\n")
    print(review_prompt(since, changes))
    if not args.full:
        print("Add --full to embed the diff itself (otherwise give the reviewer the changed files above).")
    return status


if __name__ == "__main__":
    sys.exit(main())
