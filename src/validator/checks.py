"""Nombres de los checks de los escenarios (CLAUDE.md §5 y §6) y su registro en results.json."""

from __future__ import annotations

from pathlib import Path

from validator.config import MarketConfig
from validator.evidence import Evidence
from validator.results import CheckResult, Results
from vision_engine import ScenarioReport, Verdict

STATUS = {Verdict.PASS: "pass", Verdict.FAIL: "fail", Verdict.INCONCLUSIVE: "inconclusive"}

# nombre interno de vision_engine -> (nombre en el informe, valor esperado)
CHECKS: dict[str, tuple[str, str]] = {
    "profile_calibrated": ("Juego calibrado", "calibración real del juego (calibrated: true)"),
    "spin_detected_before_click": ("Botón Spin localizado", "plantilla del Spin por encima del umbral"),
    "ready_before_click": ("Juego listo", "Spin habilitado visible antes del clic"),
    "game_setup": ("Preparación del juego verificada", "cada clic de preparación cambia la pantalla"),
    "min_bet": ("Apuesta mínima fijada", "«−» hasta que la apuesta visible (OCR) deja de bajar"),
    "initial_balance": ("Saldo del juego inicial leído", ">= 3 lecturas iguales"),
    "wager": ("Apuesta leída", ">= 3 lecturas iguales"),
    "currency": ("Moneda = {currency}", "{currency} visible en el juego"),
    "reels_started": ("Spin iniciado", "los rodillos cambian tras el clic"),
    "reels_settled": ("Spin completado", "rodillos en reposo sostenido"),
    "no_cascade_or_bonus": ("Sin bonus ni cascada pendiente", "sin movimiento tras el reposo"),
    "ready_after_settle": ("Juego listo tras el spin", "reposo + Spin habilitado"),
    "final_balance": ("Saldo del juego final leído", ">= 3 lecturas iguales"),
    "payout": ("Premio leído", "premio visible (0 si el juego lo muestra vacío al perder)"),
    "wager_consistent": ("Apuesta mostrada = apuesta usada", "misma apuesta antes y después"),
    "in_game_balance": ("Saldo del juego coherente", "después = antes - apuesta + premio"),
    "betsson_balance": ("Saldo Betsson reconcilia", "después = antes - apuesta + premio"),
    "message_visible": ("Mensaje visible", "texto en la zona de avisos tras el intento"),
    "rejection_message": ("Mensaje adecuado", "frase de saldo insuficiente del mercado"),
    "message_language": ("Idioma = {language}", "mensaje en {language}"),
    "in_game_balance_unchanged": ("Saldo del juego sin cambios", "igual antes y después"),
    "spin_rejected": ("Spin rechazado", "sin giro pagado y sin cargo"),
    "betsson_balance_unchanged": ("Saldo Betsson sin cambios", "igual antes y después"),
}

# Qué evidencia anotada respalda mejor cada check (si existe).
_IMAGE_FOR = {
    "before": ("spin_detected_before_click", "ready_before_click", "initial_balance", "wager", "currency", "min_bet"),
    "strip": ("reels_started", "reels_settled", "no_cascade_or_bonus", "spin_rejected", "game_setup"),
    "after": ("ready_after_settle", "final_balance", "payout", "wager_consistent", "in_game_balance",
              "message_visible", "rejection_message", "message_language", "in_game_balance_unchanged"),
}


def check_name(name: str, market: MarketConfig) -> tuple[str, str]:
    label, expected = CHECKS.get(name, (name, ""))
    fmt = {"currency": market.currency, "language": market.vision.language_name.lower()}
    return label.format(**fmt), expected.format(**fmt)


def record_report(results: Results, report: ScenarioReport, images: dict[str, str], evidence: Evidence,
                  market: MarketConfig, *, scenario: str, provider: str, game: str) -> None:
    """Un CheckResult por aserción del escenario, con su evidencia más representativa."""
    for assertion in report.assertions:
        label, expected = check_name(assertion.name, market)
        image = next((images[k] for k, names in _IMAGE_FOR.items() if assertion.name in names and k in images), None)
        source = image or next((e for e in assertion.evidence if e), None)
        results.add(CheckResult(
            scenario=scenario, market=market.market, provider=provider, game=game, check=label,
            status=STATUS[assertion.verdict], detail=assertion.detail, expected=expected,
            observed=assertion.detail, evidence=evidence.relative(Path(source)) if source else None,
        ))
