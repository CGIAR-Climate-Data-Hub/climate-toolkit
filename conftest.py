"""Pytest bootstrap.

Keep the repository root importable so tests can reach the ``analysis``
research scripts, which are intentionally excluded from the installed wheel.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
