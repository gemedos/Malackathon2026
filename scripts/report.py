"""Genera report.txt (RR-03), report.html y summary.md desde artifacts/<mercado>/results.json.

    python scripts/report.py            # mercado de MARKET (por defecto es)

En GitHub Actions añade además el resumen a $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vision-module")]

from validator.config import current_market, load_market  # noqa: E402
from validator.report import build  # noqa: E402


def main() -> int:
    market = load_market(current_market())
    try:
        outputs = build(market)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(outputs["summary"].read_text(encoding="utf-8"))
    print(outputs["txt"].read_text(encoding="utf-8"))
    for kind, path in outputs.items():
        print(f"{kind}: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
