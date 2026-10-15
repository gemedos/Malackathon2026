"""Alias de compatibilidad: el informe se genera con scripts/make_report.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_report import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
