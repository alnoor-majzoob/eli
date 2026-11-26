"""Export the OpenAPI contract for the generated TypeScript client.

Usage:
    python scripts/export_openapi.py [--check]

--check compares the checked-in contract with the current application and exits
non-zero on drift (used by Makefile and CI).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
TARGET = REPO_ROOT / "packages" / "api-client" / "openapi.json"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from eil.main import create_app  # noqa: E402


def render_contract() -> str:
    app = create_app()
    spec = app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the checked-in contract differs.",
    )
    args = parser.parse_args()

    content = render_contract()
    if args.check:
        if not TARGET.exists():
            print(f"OpenAPI contract missing: {TARGET}", file=sys.stderr)
            return 1
        current = TARGET.read_text(encoding="utf-8")
        if current != content:
            print(
                "OpenAPI contract is out of date. Run `make openapi` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("OpenAPI contract is up to date.")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
