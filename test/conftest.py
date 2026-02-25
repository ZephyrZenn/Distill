from __future__ import annotations

import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_SRC = _REPO_ROOT / "packages" / "distill_lib" / "src"

if str(_PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_SRC))
