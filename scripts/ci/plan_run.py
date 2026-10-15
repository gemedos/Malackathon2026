"""Planifica .github/workflows/betsson-es.yml: valida proveedor, juego, modo y salida, y reparte los juegos.

Entradas (entorno): MARKET, PROVIDER, GAME, MODE, EGRESS, EGRESS_DEFAULT, RUNNER_LABELS, CHUNK_SIZE.
Salidas ($GITHUB_OUTPUT): matrix, provider, games_json, total, runner, egress, mode, run_navigation,
run_scenarios, calibration.

Reglas:
- Los escenarios con dinero real (modos `escenarios` y `completo`) se ejecutan sobre UN juego elegido.
- Sin calibración el escenario sale INCONCLUSIVE (nunca PASS): se avisa aquí, antes de gastar nada.
- `egress=self-hosted` usa las etiquetas RUNNER_LABELS; el resto, `ubuntu-latest` con túnel.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src")]

from validator.catalog import Catalog, CatalogError, load_catalog, select_games  # noqa: E402
from validator.config import CONFIG_DIR, current_market  # noqa: E402
from validator.urls import normalize, slugify  # noqa: E402

MODES = ("navegacion", "escenarios", "completo")
EGRESS_MODES = ("self-hosted", "tailscale", "wireguard", "none")
DEFAULT_EGRESS = "self-hosted"
DEFAULT_RUNNER_LABELS = ["self-hosted", "betsson-es"]
GAMES_DIR = CONFIG_DIR / "games"


class PlanError(RuntimeError):
    """Selección imposible o peligrosa: el workflow se detiene antes de abrir betsson.es."""


@dataclass
class Plan:
    provider: str
    games: list[str]
    mode: str
    egress: str
    runner: str | list[str]
    chunk_size: int
    calibration: str
    warnings: list[str] = field(default_factory=list)

    @property
    def matrix(self) -> dict:
        chunks = [self.games[i : i + self.chunk_size] for i in range(0, len(self.games), self.chunk_size)]
        return {"include": [{"chunk": n + 1, "games": chunk} for n, chunk in enumerate(chunks)]}

    def outputs(self) -> dict[str, str]:
        return {
            "matrix": json.dumps(self.matrix, ensure_ascii=False),
            "provider": self.provider,
            "games_json": json.dumps(self.games, ensure_ascii=False),
            "total": str(len(self.games)),
            "runner": json.dumps(self.runner),
            "egress": self.egress,
            "mode": self.mode,
            "run_navigation": str(self.mode in ("navegacion", "completo")).lower(),
            "run_scenarios": str(self.mode in ("escenarios", "completo")).lower(),
            "calibration": self.calibration,
        }


def resolve_egress(requested: str | None, default: str | None) -> str:
    value = (requested or "").strip().lower()
    if value in ("", "auto"):
        value = (default or "").strip().lower() or DEFAULT_EGRESS
    if value not in EGRESS_MODES:
        raise PlanError(f"Salida {value!r} no válida. Opciones: {', '.join(EGRESS_MODES)}")
    return value


def runner_for(egress: str, labels_json: str | None) -> str | list[str]:
    if egress != "self-hosted":
        return "ubuntu-latest"
    if not (labels_json or "").strip():
        return list(DEFAULT_RUNNER_LABELS)
    try:
        labels = json.loads(labels_json)  # type: ignore[arg-type]
    except json.JSONDecodeError as exc:
        raise PlanError(f"ES_RUNNER_LABELS debe ser una lista JSON, p. ej. {json.dumps(DEFAULT_RUNNER_LABELS)}") from exc
    if not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x for x in labels):
        raise PlanError("ES_RUNNER_LABELS debe ser una lista JSON de etiquetas no vacía")
    return labels


def calibration_status(provider: str, game: str, games_dir: Path = GAMES_DIR) -> tuple[str, str | None]:
    """Misma búsqueda que validator.game.calibration.load_calibration (juego y luego `_default` del proveedor),
    sin importar la pila de visión: el job de planificación no instala OpenCV ni Tesseract."""
    base = games_dir / slugify(provider)
    path = next((p for p in (base / f"{slugify(game)}.yaml", base / "_default.yaml") if p.is_file()), None)
    if path is None:
        return "sin calibrar", (f"{provider} / {game} no tiene calibración (config/games/{slugify(provider)}/): "
                                "los escenarios saldrán INCONCLUSIVE. Calibra con scripts/calibrate.py.")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    shown = f"{slugify(provider)}/{path.name}"
    if not data.get("calibrated"):
        return f"sin terminar ({shown})", f"{shown} tiene calibrated: false: los escenarios saldrán INCONCLUSIVE."
    return f"calibrado ({shown})", None


def build_plan(
    catalog: Catalog,
    *,
    provider: str,
    game: str | None,
    mode: str,
    egress: str | None,
    egress_default: str | None = None,
    runner_labels: str | None = None,
    chunk_size: int = 20,
    games_dir: Path = GAMES_DIR,
) -> Plan:
    mode = (mode or "").strip().lower()
    if mode not in MODES:
        raise PlanError(f"Modo {mode!r} no válido. Opciones: {', '.join(MODES)}")
    try:
        resolved, games = select_games(catalog, provider, game)
    except CatalogError as exc:
        raise PlanError(str(exc)) from exc
    warnings: list[str] = []
    if provider and normalize(provider) != normalize(resolved):
        warnings.append(f"El juego elegido es de {resolved!r}, no de {provider!r}: se usa {resolved!r}")
    calibration = "no aplica"
    if mode != "navegacion":
        if len(games) != 1:
            raise PlanError("Los escenarios con dinero real se ejecutan sobre UN juego: elige un juego concreto "
                            f"(has elegido {len(games)} juegos de {resolved!r}).")
        calibration, warning = calibration_status(resolved, games[0], games_dir)
        if warning:
            warnings.append(warning)
    chosen = resolve_egress(egress, egress_default)
    if chosen == "none":
        warnings.append("egress=none: sin túnel; desde un runner de EE. UU. geo_check fallará (es lo esperado).")
    return Plan(resolved, games, mode, chosen, runner_for(chosen, runner_labels), max(1, chunk_size),
                calibration, warnings)


def main() -> int:
    env = os.environ
    try:
        plan = build_plan(
            load_catalog(current_market()),
            provider=env.get("PROVIDER", ""),
            game=env.get("GAME"),
            mode=env.get("MODE", "navegacion"),
            egress=env.get("EGRESS"),
            egress_default=env.get("EGRESS_DEFAULT"),
            runner_labels=env.get("RUNNER_LABELS"),
            chunk_size=int(env.get("CHUNK_SIZE") or 20),
        )
    except (PlanError, CatalogError, ValueError) as exc:
        print(f"::error::{exc}")
        return 1
    for warning in plan.warnings:
        print(f"::warning::{warning}")
    print(f"Proveedor: {plan.provider} · {len(plan.games)} juego(s) · modo {plan.mode} · salida {plan.egress} "
          f"· runner {json.dumps(plan.runner)} · calibración: {plan.calibration}")
    for item in plan.matrix["include"]:
        print(f"  lote {item['chunk']}: {', '.join(item['games'])}")
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            for key, value in plan.outputs().items():
                fh.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
