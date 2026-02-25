---
name: Bug Report
about: Something isn't working correctly
title: "[Bug] "
labels: bug
---

## Describe the Bug

A clear description of what's going wrong.

## Steps to Reproduce

1. Run `...`
2. See error

## Expected Behavior

What should have happened instead.

## Actual Behavior

What actually happened. Include the full error output.

## Error Output

```
Paste the full terminal output here
```

## Environment

- **OS:** (e.g., macOS 15.3, Ubuntu 24.04)
- **Python version:** (run `python3 --version`)
- **jq version:** (run `jq --version`)
- **OpenClaw version:** (if applicable)
- **Apple Music region:** (e.g., US, UK, JP)

## Checklist

- [ ] I ran `scripts/verify_setup.sh` and it passes
- [ ] My dev token is not expired (`apple_music_api.sh verify` returns 200)
- [ ] My user token is not expired
- [ ] I've redacted all tokens from the output above

## Additional Context

Any other context, screenshots, or details.
