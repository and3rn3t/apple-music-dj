#!/usr/bin/env python3
"""
generate_dev_token.py — Generate an Apple Music Developer Token (JWT)

Required env vars:
  APPLE_KEY_ID             MusicKit key ID
  APPLE_TEAM_ID            Apple Developer Team ID
  APPLE_PRIVATE_KEY_PATH   Path to the .p8 private key file

Optional:
  APPLE_TOKEN_EXPIRY       Expiry in seconds (default: 15552000 = 180 days)

Dependencies: pip install PyJWT cryptography
"""

import os
import sys
import time

def main():
    try:
        import jwt
    except ImportError:
        print("ERROR: PyJWT not installed.", file=sys.stderr)
        print("  Install: pip3 install PyJWT cryptography --break-system-packages", file=sys.stderr)
        sys.exit(1)

    key_id = os.environ.get("APPLE_KEY_ID")
    team_id = os.environ.get("APPLE_TEAM_ID")
    key_path = os.environ.get("APPLE_PRIVATE_KEY_PATH")

    missing = [v for v, val in [("APPLE_KEY_ID", key_id), ("APPLE_TEAM_ID", team_id),
               ("APPLE_PRIVATE_KEY_PATH", key_path)] if not val]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(key_path):
        print(f"ERROR: Key file not found: {key_path}", file=sys.stderr)
        sys.exit(1)

    expiry = int(os.environ.get("APPLE_TOKEN_EXPIRY", 15552000))
    with open(key_path, "r") as f:
        private_key = f.read()

    now = int(time.time())
    token = jwt.encode(
        {"iss": team_id, "iat": now, "exp": now + expiry},
        private_key, algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    print(token)
    print(f"\n✅ Token generated. Expires in {expiry // 86400} days.", file=sys.stderr)
    print(f"  export APPLE_MUSIC_DEV_TOKEN=\"{token}\"", file=sys.stderr)

if __name__ == "__main__":
    main()
