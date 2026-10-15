"""Rellena los desplegables de proveedor y juego de .github/workflows/betsson-es.yml desde el catálogo.

    python scripts/ci/render_dropdowns.py          # mercado de MARKET (por defecto es)
    python scripts/ci/render_dropdowns.py --check  # sale con 1 si el workflow no está al día

Usa los mismos marcadores (`# >>> catalog:providers` / `# >>> catalog:games`) y el mismo renderizador que
scripts/update_catalog.py, así las opciones coinciden con las de tests.yml.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from update_catalog import render_workflow  # noqa: E402
from validator.catalog import load_catalog  # noqa: E402
from validator.config import current_market  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "betsson-es.yml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="No escribe; falla si hay que regenerar")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW)
    args = parser.parse_args()

    catalog = load_catalog(current_market())
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / args.workflow.name
            shutil.copyfile(args.workflow, copy)
            stale = render_workflow(catalog, copy)
        print(f"{args.workflow.name}: {'DESACTUALIZADO' if stale else 'al día'}")
        return 1 if stale else 0
    changed = render_workflow(catalog, args.workflow)
    games = sum(len(p.games) for p in catalog.providers)
    print(f"{args.workflow.name} {'actualizado' if changed else 'sin cambios'}: "
          f"{len(catalog.providers)} proveedores, {games} juegos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
