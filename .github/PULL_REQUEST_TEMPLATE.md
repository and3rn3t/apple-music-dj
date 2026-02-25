## Description

Brief description of what this PR does.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update

## Changes Made

-

## Checklist

### Required

- [ ] All Python scripts pass syntax check: `for f in scripts/*.py; do python3 -c "import py_compile; py_compile.compile('$f', doraise=True)"; done`
- [ ] All Bash scripts pass syntax check: `for f in scripts/*.sh; do bash -n "$f"; done`
- [ ] No tokens, keys, or secrets in the diff

### If adding a new feature

- [ ] Added feature section to `SKILL.md` (triggers, run command, description)
- [ ] Added script to Scripts table in `SKILL.md`
- [ ] Added Quick Commands entry in `SKILL.md`
- [ ] Added Example Interaction in `SKILL.md`
- [ ] Updated `README.md` (features list, file structure, examples)
- [ ] Updated `CHANGELOG.md` under `[Unreleased]`

### If adding a playlist strategy

- [ ] Added algorithm to `references/playlist-strategies.md`

### If modifying API calls

- [ ] Verified against `references/api-reference.md`
- [ ] Tested with real Apple Music API (or noted if untested)

## Testing

Describe how you tested these changes:

- [ ] Ran `scripts/verify_setup.sh`
- [ ] Tested with real Apple Music account
- [ ] Tested with empty/sparse profile
- [ ] Other:

## Screenshots / Output

If applicable, paste relevant output here.
