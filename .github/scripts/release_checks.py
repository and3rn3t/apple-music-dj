#!/usr/bin/env python3
"""Release checks and ClawHub helpers used by .github/workflows/publish-clawhub.yml.

Standard library only. Kept out of scripts/ so it is never packaged into the skill.

  versions                       print the version after checking the three files agree
  check-tag TAG                  fail unless TAG == v<version>
  notes --version V [--max-chars N]   print V's CHANGELOG section (fails if missing/empty)
  write-config                   write the ClawHub CLI config from $CLAWHUB_TOKEN (0600)
  check-whoami --expect HANDLE   fail unless `clawhub whoami` reports HANDLE
  wait-for-version --slug S --version V   poll until V is ClawHub's latest
  check-verdict --slug S --version V      fail on a malicious verdict; warn on suspicious or a
                                          not-yet-generated skill card
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = "https://clawhub.ai"


class CheckError(Exception):
    """A release check failed; the message is shown to the maintainer."""


# ── versions ─────────────────────────────────────────────────────

def read_versions(root: Path = ROOT) -> dict[str, str]:
    skill = (root / "SKILL.md").read_text()
    frontmatter = skill.split("\n---\n", 1)[0]
    m_skill = re.search(r"^version:\s*(\S+)\s*$", frontmatter, re.M)
    m_py = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
    clawhub = json.loads((root / "clawhub.json").read_text()).get("version")
    found = {"SKILL.md": m_skill and m_skill.group(1), "pyproject.toml": m_py and m_py.group(1),
             "clawhub.json": clawhub}
    missing = [name for name, value in found.items() if not value]
    if missing:
        raise CheckError(f"No version found in: {', '.join(missing)}")
    return found


def agreed_version(root: Path = ROOT) -> str:
    versions = read_versions(root)
    if len(set(versions.values())) != 1:
        detail = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise CheckError(f"Version files disagree ({detail}). Bump all three together.")
    version = next(iter(versions.values()))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise CheckError(f"Version {version!r} is not plain semver (X.Y.Z)")
    return version


def check_tag(tag: str, root: Path = ROOT) -> str:
    version = agreed_version(root)
    if tag != f"v{version}":
        raise CheckError(f"Release tag {tag!r} doesn't match the version in the files (expected v{version}).")
    return version


# ── changelog ────────────────────────────────────────────────────

def changelog_section(text: str, version: str) -> str:
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not match or not match.group(1).strip():
        raise CheckError(f"CHANGELOG.md has no (non-empty) section for [{version}].")
    return match.group(1).strip()


def release_notes(version: str, max_chars: int | None = None, root: Path = ROOT) -> str:
    body = changelog_section((root / "CHANGELOG.md").read_text(), version)
    notes = f"v{version}\n\n{body}"
    if max_chars and len(notes) > max_chars:
        notes = notes[: max_chars - 40].rstrip() + "\n\n… (full notes in CHANGELOG.md)"
    return notes


# ── ClawHub CLI helpers ──────────────────────────────────────────

def write_config(path: str, token: str, registry: str = REGISTRY) -> None:
    """Write the CLI's JSON config owner-only. The token comes from the environment, never argv."""
    if not token.strip():
        raise CheckError("CLAWHUB_TOKEN is empty — add the secret to the 'clawhub' environment.")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"registry": registry, "token": token.strip()}, f)


def _run(args: list[str], run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["clawhub", *args, "--no-input"], capture_output=True, text=True)


def check_whoami(expect: str, run=subprocess.run) -> str:
    result = _run(["whoami"], run)
    handle = (result.stdout + result.stderr).strip().split()[-1:] or [""]
    if result.returncode != 0 or handle[0].lstrip("@") != expect:
        raise CheckError(f"clawhub whoami reported {handle[0]!r}, expected {expect!r} "
                         f"(is CLAWHUB_TOKEN the right account's token?).")
    return handle[0]


def wait_for_version(slug: str, version: str, timeout: float = 1200, interval: float = 20,
                     run=subprocess.run, sleep=time.sleep, clock=time.monotonic) -> None:
    deadline = clock() + timeout
    while True:
        result = _run(["inspect", slug, "--json"], run)
        if result.returncode == 0:
            try:
                latest = json.loads(result.stdout).get("latestVersion", {}).get("version")
            except json.JSONDecodeError:
                latest = None
            if latest == version:
                return
        if clock() >= deadline:
            raise CheckError(f"{slug}@{version} didn't become ClawHub's latest within {int(timeout)}s "
                             f"(still scanning, or the publish was rejected).")
        sleep(interval)


HARD_FAIL_STATUSES = {"malicious", "blocked"}


def check_verdict(slug: str, version: str, attempts: int = 4, interval: float = 30,
                  run=subprocess.run, sleep=time.sleep) -> dict:
    """Judge ClawHub's verdict for a version that is *already published*.

    - malicious/blocked: fail. An unknown status also fails (closed by default).
    - suspicious: return `_suspicious` — a warning, not a failure. ClawHub's LLM review is not
      stable (the same code has flipped between benign and suspicious on re-scans), and the
      publish has already happened, so failing the run changes nothing on the registry while
      teaching people to ignore red runs. The summary is surfaced for a human to read.
    - clean: the skill card is generated asynchronously and can lag the scans by 30+ minutes, so a
      result whose *only* problem is `card.missing` is retried briefly and then reported as
      `_card_pending` (also just a warning — metadata, not a safety property).
    An unexplained non-passing decision is never downgraded."""
    last: dict = {}
    for attempt in range(attempts):
        result = _run(["skill", "verify", slug, "--version", version], run)
        try:
            last = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise CheckError(f"Couldn't read `clawhub skill verify` output: {result.stdout[:200]!r}") from None
        security = last.get("security", {})
        status, verdict = security.get("status"), security.get("verdict")
        if status in HARD_FAIL_STATUSES or verdict in HARD_FAIL_STATUSES:
            raise CheckError(f"Security verdict for {slug}@{version} is {status or verdict!r} "
                             f"({security.get('summary', 'no summary')}). See the audit page.")
        if status == "suspicious" or (verdict == "suspicious" and status != "clean"):
            last["_suspicious"] = True
            return last
        if status != "clean" or not security.get("passed"):
            raise CheckError(f"Security verdict for {slug}@{version} is {status!r} "
                             f"({security.get('summary', 'no summary')}); expected clean. See the audit page.")
        all_reasons = last.get("reasons") or []
        other = [r for r in all_reasons if r != "card.missing"]
        if other:
            raise CheckError(f"Verification reported: {', '.join(other)}")
        if last.get("decision") == "pass":
            return last
        if "card.missing" not in all_reasons:
            # Not passing, and not because of the card: never downgrade an unexplained failure
            raise CheckError(f"Verification decision for {slug}@{version} was "
                             f"{last.get('decision')!r} with no reason given.")
        if attempt < attempts - 1:
            sleep(interval)
    last["_card_pending"] = True  # the only outstanding issue is the asynchronously generated card
    return last


# ── CLI ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("versions")
    sub.add_parser("check-tag").add_argument("tag")
    notes = sub.add_parser("notes")
    notes.add_argument("--version", required=True)
    notes.add_argument("--max-chars", type=int)
    sub.add_parser("write-config")
    sub.add_parser("check-whoami").add_argument("--expect", required=True)
    wait = sub.add_parser("wait-for-version")
    wait.add_argument("--slug", required=True)
    wait.add_argument("--version", required=True)
    wait.add_argument("--timeout", type=float, default=1200)
    verdict = sub.add_parser("check-verdict")
    verdict.add_argument("--slug", required=True)
    verdict.add_argument("--version", required=True)
    args = parser.parse_args(argv)

    try:
        if args.cmd == "versions":
            print(agreed_version())
        elif args.cmd == "check-tag":
            print(check_tag(args.tag))
        elif args.cmd == "notes":
            print(release_notes(args.version, args.max_chars))
        elif args.cmd == "write-config":
            write_config(os.environ["CLAWHUB_CONFIG_PATH"], os.environ.get("CLAWHUB_TOKEN", ""))
        elif args.cmd == "check-whoami":
            print(f"Authenticated as {check_whoami(args.expect)}")
        elif args.cmd == "wait-for-version":
            wait_for_version(args.slug, args.version, args.timeout)
            print(f"{args.slug}@{args.version} is now the latest version on ClawHub.")
        elif args.cmd == "check-verdict":
            result = check_verdict(args.slug, args.version)
            summary = result["security"].get("summary", "")
            if result.get("_suspicious"):
                print(f"::warning::ClawHub's review of {args.slug}@{args.version} says 'suspicious' (its reviews "
                      f"are not stable between runs, and this version is already published): {summary} "
                      f"Read the audit page and decide whether anything needs changing.")
                return 0
            print(f"ClawHub security verdict is clean: {summary}")
            if result.get("_card_pending"):
                print("::warning::ClawHub hasn't generated the skill card yet (it does so asynchronously, "
                      "sometimes 30+ minutes after publishing). The security verdict is clean; check "
                      "`clawhub skill verify` later.")
    except KeyError as e:
        print(f"::error::Missing environment variable {e}", file=sys.stderr)
        return 1
    except CheckError as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
