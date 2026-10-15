"""Informe a partir de `artifacts/<mercado>/results.json` (fuente única, CLAUDE.md §8).

Genera en `artifacts/<mercado>/`:
- report.txt   formato RR-03 (un bloque por escenario y juego, PASS/FAIL por check),
- report.html  tabla con esperado, observado y miniaturas de la evidencia,
- summary.md   resumen para $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import html
import json
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from validator import PROJECT_ROOT
from validator.config import MarketConfig
from validator.evidence import ARTIFACTS_DIR

SCENARIO_TITLES = {
    "navegacion": "Navegación hasta el juego en Real Play",
    "spin_completado": "Escenario 1 — Spin completado en Real Play",
    "saldo_insuficiente": "Escenario 2 — Saldo insuficiente",
}
LABEL = {"pass": "PASS", "fail": "FAIL", "inconclusive": "INCONCLUSIVE", "not_run": "NOT RUN", "error": "ERROR"}
COLOR = {"PASS": "#1a7f37", "FAIL": "#cf222e", "INCONCLUSIVE": "#9a6700", "NOT RUN": "#6e7781", "ERROR": "#8250df"}


@dataclass
class Group:
    scenario: str
    provider: str
    game: str
    checks: list[dict]

    @property
    def title(self) -> str:
        if self.scenario.startswith("sesion-"):
            return f"Sesión (cuenta {self.scenario.split('-', 1)[1].upper()})"
        return SCENARIO_TITLES.get(self.scenario, self.scenario)

    @property
    def final(self) -> str:
        """FAIL si se demostró un fallo; ERROR si falló la ejecución; PASS solo si todo pasó."""
        statuses = {c["status"] for c in self.checks}
        for status in ("fail", "error", "inconclusive", "not_run"):
            if status in statuses:
                return LABEL[status]
        return "PASS" if statuses else "NOT RUN"


def load_groups(results_path: Path) -> list[Group]:
    items = json.loads(results_path.read_text(encoding="utf-8"))
    groups: "OrderedDict[tuple, Group]" = OrderedDict()
    for item in items:
        key = (item["scenario"], item["provider"], item["game"])
        groups.setdefault(key, Group(*key, checks=[])).checks.append(item)
    return list(groups.values())


def render_text(groups: list[Group], market: MarketConfig) -> str:
    blocks = []
    for group in groups:
        lines = ["TEST REPORT", "", f"Market: {urlparse(market.base_url).netloc}",
                 f"Language: {market.vision.language_name}", f"Currency: {market.currency}", "",
                 f"Scenario: {group.title}"]
        if group.game != "-":
            lines.append(f"Game: {group.provider} / {group.game}")
        lines.append("")
        for check in group.checks:
            lines.append(f"{check['check']}: {LABEL[check['status']]}")
            if check.get("detail"):
                lines.append(f"    {check['detail']}")
        lines += ["", f"FINAL RESULT: {group.final}"]
        blocks.append("\n".join(lines))
    return ("\n\n" + "=" * 70 + "\n\n").join(blocks) + "\n"


def render_summary(groups: list[Group], market: MarketConfig) -> str:
    lines = [f"## Informe {urlparse(market.base_url).netloc} ({market.currency}, {market.vision.language_name})", "",
             "| Escenario | Juego | Resultado |", "|---|---|---|"]
    for group in groups:
        lines.append(f"| {group.title} | {group.provider} / {group.game} | **{group.final}** |")
    for group in groups:
        if group.scenario in ("spin_completado", "saldo_insuficiente"):
            lines += ["", f"### {group.title} — {group.provider} / {group.game}", "",
                      "| Check | Resultado | Detalle |", "|---|---|---|"]
            for check in group.checks:
                detail = check.get("detail", "").replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {check['check']} | {LABEL[check['status']]} | {detail} |")
    return "\n".join(lines) + "\n"


def render_html(groups: list[Group], market: MarketConfig, report_dir: Path) -> str:
    def esc(value: str) -> str:
        return html.escape(value or "")

    def evidence_cell(path: str | None) -> str:
        if not path:
            return ""
        href = esc(os.path.relpath(PROJECT_ROOT / path, report_dir))
        if path.lower().endswith(".png"):
            return f'<a href="{href}"><img src="{href}" alt="evidencia"></a>'
        return f'<a href="{href}">{esc(Path(path).name)}</a>'

    sections = []
    for group in groups:
        rows = "".join(
            f"<tr><td>{esc(c['check'])}</td>"
            f"<td><span class=st style='background:{COLOR[LABEL[c['status']]]}'>{LABEL[c['status']]}</span></td>"
            f"<td>{esc(c.get('expected', ''))}</td><td>{esc(c.get('detail', ''))}</td>"
            f"<td>{evidence_cell(c.get('evidence'))}</td></tr>"
            for c in group.checks)
        game = f" — {esc(group.provider)} / {esc(group.game)}" if group.game != "-" else ""
        sections.append(
            f"<section><h2>{esc(group.title)}{game} "
            f"<span class=st style='background:{COLOR[group.final]}'>{group.final}</span></h2>"
            f"<div class=scroll><table><tr><th>Check</th><th>Resultado</th><th>Esperado</th><th>Observado</th>"
            f"<th>Evidencia</th></tr>{rows}</table></div></section>")
    host = esc(urlparse(market.base_url).netloc)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Informe {host}</title>
<style>body{{font:14px system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px;color:#1f2328}}
h1{{font-size:22px}}h2{{font-size:17px;margin-top:28px}}.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d0d7de;padding:6px 8px;vertical-align:top;text-align:left}}
th{{background:#f6f8fa}}.st{{color:#fff;border-radius:4px;padding:2px 8px;font-weight:600;font-size:12px;white-space:nowrap}}
img{{max-width:220px;border:1px solid #d0d7de}}</style></head><body>
<h1>Informe de validación — {host}</h1>
<p>Idioma esperado: {esc(market.vision.language_name)} · Moneda esperada: {esc(market.currency)} ·
PASS solo con evidencia visual; INCONCLUSIVE = no se pudo verificar; ERROR = fallo de ejecución.</p>
{''.join(sections)}</body></html>"""


def build(market: MarketConfig) -> dict[str, Path]:
    """Genera los tres informes. Devuelve sus rutas."""
    report_dir = ARTIFACTS_DIR / market.market
    results_path = report_dir / "results.json"
    if not results_path.is_file():
        raise FileNotFoundError(f"No hay resultados en {results_path}; ejecuta antes los tests")
    groups = load_groups(results_path)
    outputs = {"txt": report_dir / "report.txt", "html": report_dir / "report.html", "summary": report_dir / "summary.md"}
    outputs["txt"].write_text(render_text(groups, market), encoding="utf-8")
    outputs["html"].write_text(render_html(groups, market, report_dir), encoding="utf-8")
    outputs["summary"].write_text(render_summary(groups, market), encoding="utf-8")
    return outputs
