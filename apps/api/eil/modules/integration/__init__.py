"""Integration module: sims' ingestion pipeline, sync orchestration, write-back.

Package bootstrap puts the repo root on ``sys.path`` so the SDK package in
``connectors/`` is importable from the API process and tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_resolved = Path(__file__).resolve()
# Source layout: <repo>/apps/api/eil/modules/integration/__init__.py -> parents[5].
# Container layout: /app/eil/modules/integration/__init__.py -> parents[3].
try:
    _REPO_ROOT = _resolved.parents[5]
except IndexError:
    _REPO_ROOT = _resolved.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import connectors  # noqa: F401,E402  (registers built-in connectors on import)
