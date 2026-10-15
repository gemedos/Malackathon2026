"""Planifica la ejecución en GitHub Actions: valida proveedor/juego y reparte los juegos en lotes.

Entradas (entorno): MARKET, PROVIDER, GAME (vacío o "(todos...)" = todos), CHUNK_SIZE.
Salidas ($GITHUB_OUTPUT): matrix (JSON para strategy.matrix), provider, total.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from validator.catalog import CatalogError, load_catalog, select_games  # noqa: E402
from validator.config import current_market  # noqa: E402
from validator.urls import normalize  # noqa: E402


def main() -> int:
    market = current_market()
    chunk_size = max(1, int(os.environ.get("CHUNK_SIZE") or 20))
    try:
        provider, games = select_games(load_catalog(market), os.environ.get("PROVIDER", ""), os.environ.get("GAME"))
    except CatalogError as exc:
        print(f"::error::{exc}")
        return 1
    requested = os.environ.get("PROVIDER", "")
    if requested and normalize(requested) != normalize(provider):
        print(f"::warning::El juego elegido es de {provider!r}, no de {requested!r}: se usa {provider!r}")
    chunks = [games[i : i + chunk_size] for i in range(0, len(games), chunk_size)]
    matrix = {"include": [{"chunk": n + 1, "games": chunk} for n, chunk in enumerate(chunks)]}
    print(f"Proveedor: {provider} · {len(games)} juego(s) en {len(chunks)} lote(s) de hasta {chunk_size}")
    for n, chunk in enumerate(chunks, 1):
        print(f"  lote {n}: {', '.join(chunk)}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"matrix={json.dumps(matrix, ensure_ascii=False)}\n")
            fh.write(f"provider={provider}\n")
            fh.write(f"total={len(games)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
