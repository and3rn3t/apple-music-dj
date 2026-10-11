"""The local mock Apple Music API now ships as scripts/demo.py (it also powers demo mode).

Kept here so tests and manual runs can still say `from tests.mock_api import MockAppleMusic` or
`python3 tests/mock_api.py [port]`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from demo import MockAppleMusic, main  # noqa: E402,F401

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8765"
    sys.exit(main(["serve", "--port", port]))
