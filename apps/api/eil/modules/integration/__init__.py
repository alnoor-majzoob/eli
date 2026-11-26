"""Integration module: sims' ingestion pipeline, sync orchestration, write-back.

Package bootstrap puts the repo root on ``sys.path`` so the SDK package in
``connectors/`` is importable from the API process and tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import connectors  # noqa: F401,E402  (registers built-in connectors on import)
