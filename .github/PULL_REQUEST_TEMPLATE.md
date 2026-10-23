## Description

Brief description of what this PR does.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change) — add the `breaking` label
- [ ] Documentation update

## Changes Made

-

## Checklist

### Required

- [ ] `make ci` passes (ruff + ShellCheck, tests at the 80% coverage floor, actionlint)
- [ ] No tokens, keys, or secrets in the diff
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (user-visible changes)
- [ ] Touches code that writes to a user's Apple Music account? Every write still needs `--yes`; add the `account-writes` label

### If adding a new feature

- [ ] Script in `scripts/`
- [ ] `SKILL.md`: feature section (triggers, run command), Scripts table row, Quick Commands entry, Example Interaction
- [ ] `README.md` features list (and the project tree if a file was added)
- [ ] `ROADMAP.md` item ticked, if it was one

### If adding a playlist strategy

- [ ] Algorithm added to `references/playlist-strategies.md`

### If changing hosts, env vars, stored files or API calls

- [ ] `SKILL.md`'s privacy section and read/write endpoint tables updated (`tests/test_trust_claims.py` checks them)
- [ ] `references/api-reference.md` updated
- [ ] A new root file is excluded in both `.clawhubignore` and `.clawignore`, or added to `ALLOWED_ROOT` in `tests/test_packaging.py`

## Testing

Describe how you tested these changes:

- [ ] Against the mock API: `python3 scripts/demo.py serve` + `APPLE_MUSIC_API_BASE` (see CONTRIBUTING.md), or `python3 scripts/demo.py run <script> …`
- [ ] With an empty/sparse profile
- [ ] Against the real Apple Music API — only if the change needs it; say what was checked
- [ ] Other:

## Screenshots / Output

If applicable, paste relevant output here.
