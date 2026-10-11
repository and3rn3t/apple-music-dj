# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.x     | ✅ Yes    |
| < 3.0   | ❌ No     |

## Reporting a Vulnerability

If you discover a security vulnerability in Apple Music DJ, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email: **<and3rn3t@icloud.com>**

Include:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment (what data could be exposed, etc.)
- Any suggested fix (optional)

### What qualifies as a security issue

- Token exposure (dev token or user token leaked in logs, output, or cache files)
- Cache files containing sensitive data beyond what's documented
- Scripts making network requests to undocumented endpoints
- File permission issues allowing unauthorized access to cached data
- Code injection via user-supplied arguments (artist names, playlist names, etc.)

### What does NOT qualify

- Apple Music API rate limiting (expected behavior)
- Token expiration (documented, not a vulnerability)
- Missing features or bugs that don't expose data

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 7 days
- **Fix (if confirmed):** Targeted within 14 days, depending on severity

## Security Best Practices for Users

1. **Never commit tokens** — Use environment variables, not hardcoded values
2. **Keep `.env` in `.gitignore`** — The repo ships with this configured
3. **Rotate tokens periodically** — Dev tokens support up to 6-month lifetime
4. **Review cache contents** — `~/.apple-music-dj/` contains your taste profile
5. **Clear the cache when sharing machines** — list it first (`ls -la ~/.apple-music-dj`), then delete
   the folder yourself. It holds your taste profile, snapshots, playlist history and cron logs, and
   deleting it can't be undone. An agent should never do this without being asked.

## How the skill handles local data

- **Owner-only files and directories.** Everything it writes about your listening (profile cache,
  `--output` files, snapshots, playlist history, config, cron logs) is mode `0600`, and
  directories it creates are `0700`. The mode is enforced on every write, so a file that already
  existed with looser permissions is tightened rather than left as it was. `~/.apple-music-dj/` itself
  is tightened to `0700`. Directories you pointed it at that already exist (e.g. `~/Documents`) are
  never changed.
- **No writing through symlinks.** An `--output` (or cache/profile) path that is a symlink, or an
  existing file owned by another user, is refused *before* anything is truncated or chmod'ed — a
  planted symlink can't be used to clobber an unrelated file. Pass the real path instead. (Stream
  devices such as `/dev/stdout` still work.)
- **No tokens on disk.** Tokens come from environment variables. The temporary curl config that
  carries them is created `0600`, deleted right after each request, and removed on Ctrl-C / `kill`.

## Scheduled jobs (cron)

Automation is **opt-in**: nothing is scheduled unless you run `setup_cron.py install`. The default
set is report-only (new releases, daily drop, health check). The two jobs that write or snapshot
(`weekly-mix`, which creates a playlist unattended, and `monthly-drift`) have to be named with `--jobs`. Because a crontab entry keeps running
until removed, the installer is deliberately strict:

- **Installing requires confirmation, enforced in code.** `install --dry-run` prints the exact
  crontab lines and a short digest of them; `install` only proceeds when re-run with
  `--confirm <digest>`. A bare `install` changes nothing and exits 2, and a digest only matches the
  lines it was printed for, so approving one set of jobs/paths can't authorize another.
- `--jobs` must name at least one known job (an empty value is an error, never "all jobs"; unknown
  names are rejected up front, including for `remove`).
- `--profile`, `--log-dir`, `--python`, `--storefront` and `--jobs` are validated: paths must not
  contain newlines, control characters or `%` (cron turns `%` into a newline, even inside quotes),
  `--python` must be an executable file, and the storefront must be a two-letter code.
- Every value is shell-quoted, including the log path, and a finished line containing a newline or
  `%` is refused.
- Jobs run under `umask 077`. Log files are created `0600` in a `0700` directory *before* cron
  writes to them (they contain playlist names, track picks and artist preferences). A symlinked log
  directory or file, a directory or file owned by someone else, or a directory other users can
  write to is rejected.
- `setup_cron.py status` shows what is installed; `setup_cron.py remove` takes it out again.
