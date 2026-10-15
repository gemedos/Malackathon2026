"""Lanzador interactivo: elige proveedor, luego solo sus juegos, y ejecuta en local o en GitHub Actions.

    python scripts/run_tests.py
    python scripts/run_tests.py --provider "Pragmatic Play" --game "Sweet Bonanza" --where local
    python scripts/run_tests.py --provider "PlaynGo" --where github        # todos los juegos de PlaynGo

En cada menú puedes escribir un número o un texto para filtrar la lista.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from validator.catalog import ALL_GAMES_OPTION, OPTION_SEPARATOR, Catalog, load_catalog, select_games  # noqa: E402
from validator.config import current_market  # noqa: E402
from validator.urls import normalize  # noqa: E402

WORKFLOW = "tests.yml"
PAGE = 40  # máximo de opciones mostradas a la vez


def choose(title: str, items: list[str], *, allow_all: str | None = None) -> str | None:
    """Menú con filtro por texto. Devuelve el elemento elegido, o None si se elige `allow_all`."""
    shown = items
    while True:
        print(f"\n== {title} ({len(shown)} de {len(items)}) ==")
        if allow_all:
            print(f"   0. {allow_all}")
        for i, item in enumerate(shown[:PAGE], 1):
            print(f"  {i:>2}. {item}")
        if len(shown) > PAGE:
            print(f"  ... {len(shown) - PAGE} más: escribe parte del nombre para filtrar")
        hint = "número, texto para filtrar" + (", Enter = " + allow_all if allow_all else "")
        answer = input(f"Elige ({hint}): ").strip()
        if not answer:
            if allow_all:
                return None
            shown = items
            continue
        if answer.isdigit():
            n = int(answer)
            if allow_all and n == 0:
                return None
            if 1 <= n <= min(len(shown), PAGE):
                return shown[n - 1]
            print("Número fuera de rango.")
            continue
        exact = [i for i in items if normalize(i) == normalize(answer)]
        if len(exact) == 1:
            return exact[0]
        filtered = [i for i in items if normalize(answer) in normalize(i)]
        if len(filtered) == 1:
            return filtered[0]
        if not filtered:
            print(f"Nada coincide con {answer!r}.")
        else:
            shown = filtered


def run_local(provider: str, game: str | None) -> int:
    cmd = [sys.executable, "-m", "pytest", "tests", "--ignore=tests/test_secret_hygiene.py", "--provider", provider]
    if game:
        cmd += ["--game", game]
    print("\n$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    code = subprocess.call(cmd, cwd=ROOT)
    print("\n$ pytest tests/test_secret_hygiene.py")
    hygiene = subprocess.call([sys.executable, "-m", "pytest", "tests/test_secret_hygiene.py", "-q"], cwd=ROOT)
    return code or hygiene


def run_github(provider: str, game: str | None) -> int:
    if shutil.which("gh") is None:
        print("No se encontró la CLI 'gh'. Instálala o lanza el workflow desde la web.")
        return 1
    game_option = f"{provider}{OPTION_SEPARATOR}{game}" if game else ALL_GAMES_OPTION
    cmd = ["gh", "workflow", "run", WORKFLOW, "-f", f"provider={provider}", "-f", f"game={game_option}"]
    print("\n$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    code = subprocess.call(cmd, cwd=ROOT)
    if code == 0:
        print("Lanzado. Sigue la ejecución con:  gh run watch")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider")
    parser.add_argument("--game", help=f"nombre del juego; omítelo o usa '{ALL_GAMES_OPTION}' para todos")
    parser.add_argument("--where", choices=("local", "github"))
    parser.add_argument("--yes", action="store_true", help="no pedir confirmación")
    args = parser.parse_args()

    catalog: Catalog = load_catalog(current_market())
    print(f"Catálogo {catalog.market}: {len(catalog.providers)} proveedores (scrape {catalog.scraped_at})")

    provider = args.provider or choose("Proveedor", [p.name for p in catalog.providers])
    provider_entry = catalog.provider(provider)
    if args.game is not None or args.provider:
        game = None if not args.game or args.game == ALL_GAMES_OPTION else args.game
    else:
        game = choose(f"Juegos de {provider_entry.name}", [g.name for g in provider_entry.games],
                      allow_all=ALL_GAMES_OPTION)
    provider, games = select_games(catalog, provider_entry.name, game)  # valida contra el catálogo

    where = args.where or ("github" if choose("¿Dónde ejecutar?", ["local", "github"]) == "github" else "local")
    target = games[0] if game else f"todos ({len(games)} juegos)"
    print(f"\nProveedor: {provider}\nJuego:     {target}\nDónde:     {where}")
    print("Se abrirá el juego en Real Play con la cuenta FUNDED (sin hacer spins).")
    if not args.yes and input("¿Continuar? [s/N]: ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
        return 1
    return run_local(provider, games[0] if game else None) if where == "local" else run_github(provider, games[0] if game else None)


if __name__ == "__main__":
    sys.exit(main())
