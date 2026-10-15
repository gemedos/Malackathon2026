"""Actualiza el catálogo de proveedores/juegos y los desplegables del workflow.

    python scripts/update_catalog.py                 # scrape + catálogo + workflow
    python scripts/update_catalog.py --render-only   # solo regenera el workflow desde el catálogo

GitHub solo admite opciones estáticas en `workflow_dispatch`, así que las listas `options:` de
.github/workflows/tests.yml se reescriben entre los marcadores `# >>> catalog:<lista>` y `# <<< catalog:<lista>`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from validator import PROJECT_ROOT  # noqa: E402
from validator.catalog import (  # noqa: E402
    ALL_GAMES_OPTION, Catalog, catalog_path, load_catalog, save_catalog, scrape_catalog,
)
from validator.config import current_market, load_market  # noqa: E402

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
log = logging.getLogger("update_catalog")


def render_workflow(catalog: Catalog, path: Path = WORKFLOW) -> bool:
    """Reescribe las opciones de los desplegables. Devuelve True si el archivo cambió."""
    lists = {
        "providers": [p.name for p in catalog.providers],
        "games": [ALL_GAMES_OPTION, *catalog.game_options()],
    }
    text = path.read_text(encoding="utf-8")
    new = text
    for name, options in lists.items():
        pattern = re.compile(
            rf"(?P<head>^(?P<indent>[ \t]*)# >>> catalog:{name}[^\n]*\n)(?P<body>.*?)(?P<tail>^[ \t]*# <<< catalog:{name}[^\n]*$)",
            re.M | re.S,
        )
        match = pattern.search(new)
        if match is None:
            raise SystemExit(f"Faltan los marcadores 'catalog:{name}' en {path}")
        indent = match.group("indent")
        # json.dumps produce cadenas YAML válidas (comillas dobles con escapes).
        body = "".join(f"{indent}- {json.dumps(o, ensure_ascii=False)}\n" for o in options)
        new = new[: match.start("body")] + body + new[match.end("body"):]
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")  # LF también en runners Windows
        return True
    return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true", help="No hace scrape; usa el catálogo guardado")
    parser.add_argument("--headed", action="store_true", help="Muestra el navegador durante el scrape")
    args = parser.parse_args()

    market = load_market(current_market())
    if args.render_only:
        catalog = load_catalog(market.market)
    else:
        catalog = scrape_catalog(market, headless=not args.headed)
        try:
            previous = load_catalog(market.market)
        except Exception:
            previous = None
        if previous is not None and previous.content_key() == catalog.content_key():
            log.info("El catálogo no ha cambiado (se conserva scraped_at=%s)", previous.scraped_at)
            catalog = previous
        else:
            log.info("Catálogo guardado en %s", save_catalog(catalog).relative_to(PROJECT_ROOT))
    changed = render_workflow(catalog)
    games = sum(len(p.games) for p in catalog.providers)
    log.info("Workflow %s: %d proveedores, %d juegos", "actualizado" if changed else "sin cambios",
             len(catalog.providers), games)
    return 0


if __name__ == "__main__":
    sys.exit(main())
