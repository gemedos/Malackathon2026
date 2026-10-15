"""Genera el informe de la ejecución a partir de artifacts/<mercado>/results.json (fuente única).

    python scripts/make_report.py                       # artifacts/es/results.json -> artifacts/es/report.*
    python scripts/make_report.py <results.json> [<report.html>]

Salidas junto al JSON: report.html (resumen ejecutivo, aserciones de negocio y todos los checks con evidencia),
report.txt (formato RR-03) y summary.md (resumen para GitHub Actions).

Reglas del informe:
- Un criterio de negocio solo es APROBADO si TODOS los checks que lo respaldan pasaron. Si falta alguno aparece
  como «NO EJECUTADO»: nunca se da por aprobado lo que no se ejecutó.
- Proveedor, juego y mercado salen del propio JSON, así que sirve para cualquier juego (y para varios en un run).
"""

from __future__ import annotations

import html
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vision-module")]

DEFAULT_SRC = ROOT / "artifacts" / "es" / "results.json"

# Criterios de negocio oficiales -> nombres EXACTOS de los checks que los demuestran (src/validator/checks.py y
# vision_engine). Todos deben pasar.
SCENARIOS = {
    "spin_completado": {
        "title": "Escenario 1 — Spin completado en Real Play",
        "assertions": [
            ("El giro realmente comenzó y se completó (hacer clic en el control no basta).",
             ["Spin iniciado", "Spin completado"]),
            ("La apuesta mostrada coincide con la apuesta utilizada para el giro.",
             ["Apuesta leída", "Apuesta mostrada = apuesta usada"]),
            ("La divisa mostrada coincide con el mercado objetivo.", ["Moneda = EUR"]),
            ("El saldo dentro del juego es coherente: antes − apuesta + premio = después.",
             ["Saldo del juego inicial leído", "Saldo del juego final leído", "Premio leído",
              "Saldo del juego coherente"]),
            ("El saldo de la cuenta Betsson refleja el mismo giro.", ["Saldo Betsson reconcilia"]),
        ],
    },
    "saldo_insuficiente": {
        "title": "Escenario 2 — Saldo insuficiente",
        "assertions": [
            ("El intento de giro es rechazado en lugar de completarse como un giro de pago.", ["Spin rechazado"]),
            ("El jugador recibe un mensaje adecuado de saldo insuficiente, en el idioma esperado.",
             ["Mensaje visible", "Mensaje adecuado", "Idioma = español"]),
            ("La divisa mostrada coincide con el mercado objetivo.", ["Moneda = EUR"]),
            ("El saldo de Betsson no cambia.", ["Saldo Betsson sin cambios"]),
            ("El saldo dentro del juego no cambia.", ["Saldo del juego sin cambios"]),
        ],
    },
}
SCENARIO_ORDER = ["spin_completado", "saldo_insuficiente"]

LABEL = {"pass": "APROBADO", "fail": "FALLIDO", "inconclusive": "INCONCLUSO", "not_run": "NO EJECUTADO",
         "error": "ERROR"}
CSS_CLASS = {"pass": "ok", "fail": "ko", "inconclusive": "inc", "not_run": "nr", "error": "err"}
SEVERITY = ["fail", "error", "inconclusive", "not_run"]      # el peor estado manda; si no hay ninguno, pass


def esc(value) -> str:
    return html.escape("—" if value is None or value == "" else str(value))


def badge(status: str) -> str:
    return f'<span class="b {CSS_CLASS.get(status, "inc")}">{esc(LABEL.get(status, str(status).upper()))}</span>'


def worst(statuses) -> str:
    statuses = set(statuses)
    for status in SEVERITY:
        if status in statuses:
            return status
    return "pass" if statuses else "not_run"


def table(headers, rows) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><tr>{head}</tr>{body}</table></div>'


def load_results(path: Path) -> list[dict]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"{path} no contiene una lista de resultados")
    return items


def group_runs(items: list[dict]) -> "OrderedDict[tuple, list[dict]]":
    groups: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for item in items:
        groups.setdefault((item["scenario"], item["provider"], item["game"]), []).append(item)
    return groups


def evaluate(checks: list[dict], assertions) -> list[dict]:
    """Estado de cada criterio de negocio a partir de los checks que lo respaldan."""
    by_name = {c["check"]: c for c in checks}
    rows = []
    for description, names in assertions:
        found = [by_name[n] for n in names if n in by_name]
        missing = [n for n in names if n not in by_name]
        status = worst([c["status"] for c in found] + (["not_run"] if missing else []))
        detail = " · ".join(f"{c['check']}: {c.get('detail', '')}" for c in found)
        if missing:
            detail = (detail + " · " if detail else "") + "Sin ejecutar: " + ", ".join(missing)
        rows.append({"description": description, "status": status, "detail": detail})
    return rows


def evidence_cell(path: str | None, report_dir: Path) -> str:
    if not path:
        return ""
    target = ROOT / path
    href = esc(os.path.relpath(target, report_dir)).replace("\\", "/") if target.exists() else esc(path)
    if path.lower().endswith(".png"):
        return f'<a href="{href}"><img src="{href}" alt="evidencia"></a>'
    return f'<a href="{href}">{esc(Path(path).name)}</a>'


def market_info(market_key: str) -> tuple[str, str, str]:
    """(dominio, divisa, idioma) del mercado; si la configuración no se puede leer, valores neutros."""
    try:
        from validator.config import load_market
        market = load_market(market_key)
        return urlparse(market.base_url).netloc, market.currency, market.vision.language_name
    except Exception:
        return f"betsson.{market_key}", "—", "—"


def render_html(groups, report_dir: Path, market_key: str) -> str:
    domain, currency, language = market_info(market_key)
    summary_rows, sections, total = [], [], 0
    ordered = sorted(groups.items(), key=lambda kv: (SCENARIO_ORDER.index(kv[0][0]) if kv[0][0] in SCENARIO_ORDER
                                                     else len(SCENARIO_ORDER), 0))
    for (scenario, provider, game), checks in ordered:
        definition = SCENARIOS.get(scenario)
        game_label = f"{provider} / {game}" if game != "-" else provider
        if definition is None:                       # sesiones (login) y cualquier otro grupo: solo sus checks
            title = f"Sesión (cuenta {scenario.split('-', 1)[1].upper()})" if scenario.startswith("sesion-") else scenario
            status = worst(c["status"] for c in checks)
            summary_rows.append([esc(title), esc(game_label), badge(status), f"{len(checks)} checks"])
            continue
        rows = evaluate(checks, definition["assertions"])
        total += len(rows)
        status = worst(r["status"] for r in rows + [{"status": c["status"]} for c in checks])
        summary_rows.append([esc(definition["title"]), esc(game_label), badge(status), f"{len(rows)} criterios"])
        criteria = table(["Estado", "Criterio de negocio", "Evidencia observada"],
                         [[badge(r["status"]), esc(r["description"]), esc(r["detail"])] for r in rows])
        detail = table(["Check", "Resultado", "Esperado", "Observado", "Evidencia"],
                       [[esc(c["check"]), badge(c["status"]), esc(c.get("expected")), esc(c.get("detail")),
                         evidence_cell(c.get("evidence"), report_dir)] for c in checks])
        sections.append(f"""<section>
<h2>{esc(definition['title'])} {badge(status)}</h2>
<p><b>Mercado:</b> {esc(domain)} · <b>Proveedor:</b> {esc(provider)} · <b>Juego:</b> {esc(game)}</p>
<h3>Criterios de negocio</h3>{criteria}
<details><summary>Todos los checks y evidencias ({len(checks)})</summary>{detail}</details>
</section>""")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Reporte PoC {esc(domain)}</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}}
 .scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;margin:.5rem 0 1rem}}
 th,td{{border:1px solid #ddd;padding:8px 12px;text-align:left;vertical-align:top}} th{{background:#f4f4f4}}
 .b{{padding:2px 8px;border-radius:6px;font-size:.8em;font-weight:bold;white-space:nowrap}}
 .ok{{background:#d8f5d8;color:#0a5c0a}} .ko{{background:#fbd5d5;color:#900}} .inc{{background:#fff3cd;color:#856404}}
 .nr{{background:#e8eaed;color:#444}} .err{{background:#e9dcfb;color:#5b2a9e}}
 img{{max-width:200px;border:1px solid #ddd}} details{{margin:.5rem 0 1rem}} summary{{cursor:pointer;font-weight:600}}
</style></head><body>
<h1>Reporte PoC: validación visual en {esc(domain)} ({esc(currency)})</h1>
<p>Idioma esperado: {esc(language)} · Divisa: {esc(currency)} · Criterios de negocio evaluados: {total}.
APROBADO solo con evidencia visual; INCONCLUSO = no se pudo verificar; NO EJECUTADO = faltan checks; ERROR = fallo de ejecución.</p>
<h2>Resumen ejecutivo</h2>{table(["Escenario", "Juego", "Resultado", "Alcance"], summary_rows)}
{''.join(sections)}
<h2>Seguridad y cumplimiento</h2>
<ul><li>Credenciales gestionadas con variables de entorno / GitHub Secrets.</li>
<li>Sin credenciales en repositorio, capturas ni reporte.</li>
<li>Usuario enmascarado.</li></ul>
<h2>Limitaciones</h2>
<ul><li>Dependencia de IP española (ejecutor local).</li>
<li>Fragilidad ante cambios de interfaz del proveedor.</li>
<li>Posibles errores de lectura visual, mitigados con lecturas múltiples y umbrales de confianza.</li></ul>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):      # la consola de Windows (cp1252) no admite «→» y otros símbolos
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:] if argv is None else argv
    src = Path(args[0]) if args else DEFAULT_SRC
    if not src.exists() and not src.is_absolute() and (ROOT / src).exists():
        src = ROOT / src                         # funciona lanzado desde cualquier carpeta
    if not src.exists():
        print(f"ERROR: no se encuentra {src}. Ejecuta antes las pruebas (python run.py).", file=sys.stderr)
        return 1
    report_dir = src.resolve().parent
    out = Path(args[1]) if len(args) > 1 else report_dir / "report.html"
    items = load_results(src)
    groups = group_runs(items)
    market_key = items[0].get("market", "es") if items else "es"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(groups, report_dir, market_key), encoding="utf-8")
    written = {"html": out}
    try:                                         # report.txt (RR-03) y summary.md reutilizan el módulo del validador
        from validator.config import load_market
        from validator.report import load_groups, render_summary, render_text
        market = load_market(market_key)
        text_groups = load_groups(src)
        (report_dir / "report.txt").write_text(render_text(text_groups, market), encoding="utf-8")
        (report_dir / "summary.md").write_text(render_summary(text_groups, market), encoding="utf-8")
        written.update(txt=report_dir / "report.txt", summary=report_dir / "summary.md")
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a", encoding="utf-8") as fh:
                fh.write((report_dir / "summary.md").read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Aviso: no se generaron report.txt / summary.md ({type(exc).__name__}: {exc})", file=sys.stderr)
    print(f"Reporte generado correctamente: {out}")
    for kind, path in written.items():
        print(f"  {kind}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
