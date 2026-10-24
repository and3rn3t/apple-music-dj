"""The Tests workflow's docs-only path: which PRs take it, and which tests it runs."""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())
JOBS = WORKFLOW["jobs"]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
PRE_COMMIT = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
DOC_READING = re.compile(r"\.md|README|SKILL|ROADMAP|CHANGELOG|references|assets/")


def step(job: str, name: str) -> dict:
    return next(s for s in JOBS[job]["steps"] if s.get("name") == name)


def docs_job_tests() -> set[str]:
    return set(re.findall(r"tests/test_\w+\.py", step("docs", "Run the docs tests")["run"]))


def test_docs_job_runs_every_test_that_reads_docs_or_assets():
    readers = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py")
               if p.name != Path(__file__).name and DOC_READING.search(p.read_text())}
    missing = readers - docs_job_tests()
    assert not missing, f"add to the docs job in test.yml (they read docs/assets): {sorted(missing)}"


def test_docs_job_lists_only_real_files():
    assert docs_job_tests()
    for path in docs_job_tests():
        assert (ROOT / path).is_file(), path


def test_every_job_reports_into_the_ci_result():
    assert set(JOBS["result"]["needs"]) == set(JOBS) - {"result"}
    assert JOBS["result"]["if"] == "always()"


@pytest.mark.skipif(not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash")
@pytest.mark.parametrize("files, code", [
    (["README.md"], "false"),
    (["references/auth-setup.md", "assets/icon.svg", "LICENSE"], "false"),
    ([".github/ISSUE_TEMPLATE/bug_report.yml", "SKILL.md"], "false"),
    (["README.md", "scripts/demo.py"], "true"),
    ([".github/workflows/test.yml"], "true"),
    (["pyproject.toml"], "true"),
])
def test_classify_step_on_a_pr_merge_commit(tmp_path, files, code):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    (tmp_path / "base.txt").write_text("base\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "pr")
    for name in files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("changed\n")
    git("add", "-A")
    git("commit", "-qm", "pr")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "-m", "merge", "pr")  # like refs/pull/N/merge: parent 1 is the base

    out, summary = tmp_path / "out", tmp_path / "summary"
    env = {**os.environ, "EVENT": "pull_request", "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary)}
    subprocess.run(["bash", "-c", step("changes", "Classify the changed files")["run"]],
                   cwd=tmp_path, env=env, check=True, capture_output=True)
    assert out.read_text().strip() == f"code={code}"


def test_classify_step_runs_everything_on_push(tmp_path):
    out = tmp_path / "out"
    env = {**os.environ, "EVENT": "push", "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(tmp_path / "s")}
    subprocess.run(["bash", "-c", step("changes", "Classify the changed files")["run"]],
                   cwd=tmp_path, env=env, check=True, capture_output=True)
    assert out.read_text().strip() == "code=true"


def dev_pin(package: str) -> str:
    pins = [d.split("==", 1)[1] for d in PYPROJECT["project"]["optional-dependencies"]["dev"]
            if d.startswith(f"{package}==")]
    assert pins, f"pin {package} with == in the [dev] extra"
    return pins[0]


def pre_commit_rev(repo_suffix: str) -> str:
    return next(r["rev"] for r in PRE_COMMIT["repos"] if r["repo"].endswith(repo_suffix)).removeprefix("v")


def test_ruff_pin_matches_pre_commit():
    assert dev_pin("ruff") == pre_commit_rev("/ruff-pre-commit")


def test_shellcheck_pin_matches_pre_commit():
    # shellcheck-py versions are the ShellCheck version plus a packaging suffix: 0.11.0.1 is 0.11.0.
    assert dev_pin("shellcheck-py").rsplit(".", 1)[0] == pre_commit_rev("/shellcheck-precommit")


def test_matrix_tests_every_advertised_python():
    prefix = "Programming Language :: Python :: 3."
    advertised = {c.removeprefix("Programming Language :: Python :: ")
                  for c in PYPROJECT["project"]["classifiers"] if c.startswith(prefix)}
    assert set(JOBS["test"]["strategy"]["matrix"]["python-version"]) == advertised


def test_release_runs_the_full_ci_gate():
    publish = yaml.safe_load((ROOT / ".github" / "workflows" / "publish-clawhub.yml").read_text())
    run = next(s for s in publish["jobs"]["verify"]["steps"] if s.get("name") == "Lint and test")["run"]
    assert '-e ".[dev]"' in run
    assert "make ruff coverage" in run
