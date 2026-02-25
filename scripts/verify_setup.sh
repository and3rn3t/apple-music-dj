#!/usr/bin/env bash
# verify_setup.sh — Check all prerequisites for Apple Music DJ
# Run this once after install to verify everything is ready.

set -euo pipefail

PASS="✅"
FAIL="❌"
WARN="⚠️"
errors=0
warnings=0

echo "🎧 Apple Music DJ — Setup Verification"
echo "========================================"
echo ""

# ── Required binaries ──────────────────────────────────────

echo "Checking required tools..."

for bin in curl jq python3; do
    if command -v "$bin" &>/dev/null; then
        version=$("$bin" --version 2>&1 | head -1)
        echo "  $PASS $bin — $version"
    else
        echo "  $FAIL $bin — NOT FOUND"
        errors=$((errors + 1))
    fi
done

echo ""

# ── Python version check ──────────────────────────────────

echo "Checking Python version..."
py_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
py_major=$(echo "$py_version" | cut -d. -f1)
py_minor=$(echo "$py_version" | cut -d. -f2)

if [[ "$py_major" -ge 3 && "$py_minor" -ge 8 ]]; then
    echo "  $PASS Python $py_version (≥ 3.8 required)"
else
    echo "  $FAIL Python $py_version (≥ 3.8 required)"
    errors=$((errors + 1))
fi

echo ""

# ── Optional: PyJWT (only for token generation) ───────────

echo "Checking optional dependencies..."
if python3 -c "import jwt" 2>/dev/null; then
    echo "  $PASS PyJWT — installed (needed for token generation)"
else
    echo "  $WARN PyJWT — not installed (only needed if generating dev tokens locally)"
    echo "       Install with: pip3 install PyJWT"
    warnings=$((warnings + 1))
fi

echo ""

# ── Environment variables ─────────────────────────────────

echo "Checking environment variables..."

if [[ -n "${APPLE_MUSIC_DEV_TOKEN:-}" ]]; then
    token_len=${#APPLE_MUSIC_DEV_TOKEN}
    echo "  $PASS APPLE_MUSIC_DEV_TOKEN — set ($token_len chars)"
else
    echo "  $FAIL APPLE_MUSIC_DEV_TOKEN — NOT SET"
    echo "       See references/auth-setup.md for instructions"
    errors=$((errors + 1))
fi

if [[ -n "${APPLE_MUSIC_USER_TOKEN:-}" ]]; then
    token_len=${#APPLE_MUSIC_USER_TOKEN}
    echo "  $PASS APPLE_MUSIC_USER_TOKEN — set ($token_len chars)"
else
    echo "  $FAIL APPLE_MUSIC_USER_TOKEN — NOT SET"
    echo "       See references/auth-setup.md for instructions"
    errors=$((errors + 1))
fi

if [[ -n "${APPLE_MUSIC_STOREFRONT:-}" ]]; then
    echo "  $PASS APPLE_MUSIC_STOREFRONT — ${APPLE_MUSIC_STOREFRONT} (override)"
else
    echo "  $WARN APPLE_MUSIC_STOREFRONT — not set (will auto-detect)"
fi

echo ""

# ── Script files ──────────────────────────────────────────

echo "Checking scripts..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

expected_scripts=(
    "apple_music_api.sh"
    "taste_profiler.py"
    "build_playlist.sh"
    "generate_dev_token.py"
    "taste_card.py"
    "compatibility.py"
    "listening_insights.py"
    "catalog_explorer.py"
    "daily_pick.py"
    "concert_prep.sh"
    "new_releases.sh"
    "verify_setup.sh"
)

for script in "${expected_scripts[@]}"; do
    if [[ -f "$SCRIPT_DIR/$script" ]]; then
        echo "  $PASS $script"
    else
        echo "  $FAIL $script — MISSING"
        errors=$((errors + 1))
    fi
done

echo ""

# ── API connectivity ──────────────────────────────────────

echo "Checking API connectivity..."

if [[ -n "${APPLE_MUSIC_DEV_TOKEN:-}" && -n "${APPLE_MUSIC_USER_TOKEN:-}" ]]; then
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${APPLE_MUSIC_DEV_TOKEN}" \
        -H "Music-User-Token: ${APPLE_MUSIC_USER_TOKEN}" \
        "https://api.music.apple.com/v1/me/recent/played/tracks?limit=1" \
        2>/dev/null || echo "000")

    case "$http_code" in
        200)
            echo "  $PASS Apple Music API — connected (HTTP $http_code)"
            ;;
        401)
            echo "  $FAIL Dev token invalid or expired (HTTP 401)"
            echo "       Regenerate with: python3 scripts/generate_dev_token.py"
            errors=$((errors + 1))
            ;;
        403)
            echo "  $FAIL User token expired (HTTP 403)"
            echo "       Re-authorize via MusicKit JS in browser"
            errors=$((errors + 1))
            ;;
        429)
            echo "  $WARN Rate limited (HTTP 429) — API is reachable, try again shortly"
            warnings=$((warnings + 1))
            ;;
        000)
            echo "  $FAIL Network error — cannot reach api.music.apple.com"
            errors=$((errors + 1))
            ;;
        *)
            echo "  $WARN Unexpected response (HTTP $http_code)"
            warnings=$((warnings + 1))
            ;;
    esac
else
    echo "  $WARN Skipped — tokens not set"
fi

echo ""

# ── Cache status ──────────────────────────────────────────

echo "Checking cache..."

cache_file="${HOME}/.apple-music-dj/taste_profile.json"
if [[ -f "$cache_file" ]]; then
    cache_size=$(wc -c < "$cache_file" | tr -d ' ')
    cache_mod=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$cache_file" 2>/dev/null || { stat -c "%y" "$cache_file" 2>/dev/null | cut -d. -f1; })
    echo "  $PASS Taste profile cached ($cache_size bytes, last modified: $cache_mod)"
else
    echo "  $WARN No cached taste profile yet"
    echo "       Run: python3 scripts/taste_profiler.py"
fi

echo ""

# ── Summary ───────────────────────────────────────────────

echo "========================================"
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
    echo "$PASS All checks passed! You're ready to go."
elif [[ $errors -eq 0 ]]; then
    echo "$WARN All critical checks passed ($warnings warning(s))"
else
    echo "$FAIL $errors error(s), $warnings warning(s)"
    echo "  Fix the issues above before using the skill."
fi

exit $errors
