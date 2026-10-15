"""Planificación y comprobación de red de betsson-es.yml (scripts/ci/), sin red ni navegador."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts" / "ci"), str(ROOT / "scripts")]

import geo_check  # noqa: E402
import plan_run  # noqa: E402
from plan_run import PlanError, build_plan  # noqa: E402
from update_catalog import render_workflow  # noqa: E402
from validator.catalog import ALL_GAMES_OPTION, Catalog, CatalogGame, CatalogProvider, load_catalog  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "betsson-es.yml"


def _catalog() -> Catalog:
    def games(*names: str) -> list[CatalogGame]:
        return [CatalogGame(id=n, name=n, slug=n.lower().replace(" ", "-"), type="Slots") for n in names]

    return Catalog(market="es", scraped_at="2026-10-15T00:00:00Z", source="test", providers=[
        CatalogProvider(name="Pragmatic Play", slug="pragmatic-play", games=games("Sweet Bonanza", "Gates of Olympus")),
        CatalogProvider(name="PlaynGo", slug="playngo", games=games(*[f"Juego {i}" for i in range(45)])),
    ])


def _plan(**kw):
    defaults = {"provider": "Pragmatic Play", "game": "Sweet Bonanza", "mode": "navegacion", "egress": "auto"}
    return build_plan(_catalog(), **{**defaults, **kw})


# ------------------------------------------------------------------------ plan


def test_navegacion_de_todos_los_juegos_en_lotes() -> None:
    plan = _plan(provider="PlaynGo", game=ALL_GAMES_OPTION, chunk_size=20)
    assert [len(c["games"]) for c in plan.matrix["include"]] == [20, 20, 5]
    out = plan.outputs()
    assert out["run_navigation"] == "true" and out["run_scenarios"] == "false"
    assert out["calibration"] == "no aplica"


@pytest.mark.parametrize("mode", ["escenarios", "completo"])
def test_escenarios_exigen_un_juego(mode: str) -> None:
    with pytest.raises(PlanError, match="UN juego"):
        _plan(game=ALL_GAMES_OPTION, mode=mode)


def test_escenarios_de_pragmatic_usan_la_calibracion_del_proveedor() -> None:
    plan = _plan(mode="completo")
    assert plan.calibration.startswith("calibrado")
    assert not plan.warnings
    assert json.loads(plan.outputs()["games_json"]) == ["Sweet Bonanza"]


def test_escenarios_sin_calibracion_avisan_inconclusive() -> None:
    plan = _plan(provider="PlaynGo", game="PlaynGo / Juego 3", mode="escenarios")
    assert plan.calibration == "sin calibrar"
    assert any("INCONCLUSIVE" in w for w in plan.warnings)


def test_el_proveedor_del_juego_manda() -> None:
    plan = _plan(provider="PlaynGo", game="Pragmatic Play / Gates of Olympus")
    assert plan.provider == "Pragmatic Play" and plan.games == ["Gates of Olympus"]
    assert any("se usa" in w for w in plan.warnings)


def test_modo_y_juego_invalidos() -> None:
    with pytest.raises(PlanError, match="Modo"):
        _plan(mode="todo")
    with pytest.raises(PlanError, match="no está en el catálogo"):
        _plan(game="No Existe")


@pytest.mark.parametrize("requested,default,expected", [
    ("auto", None, "self-hosted"),
    ("", "tailscale", "tailscale"),
    ("auto", "wireguard", "wireguard"),
    ("none", "tailscale", "none"),
])
def test_resolucion_de_salida(requested, default, expected) -> None:
    assert plan_run.resolve_egress(requested, default) == expected


def test_salida_invalida() -> None:
    with pytest.raises(PlanError):
        plan_run.resolve_egress("vpn", None)


def test_runner_segun_salida() -> None:
    assert plan_run.runner_for("tailscale", None) == "ubuntu-latest"
    assert plan_run.runner_for("self-hosted", "") == ["self-hosted", "betsson-es"]
    assert plan_run.runner_for("self-hosted", '["self-hosted","linux","madrid"]') == ["self-hosted", "linux", "madrid"]
    with pytest.raises(PlanError):
        plan_run.runner_for("self-hosted", "madrid")
    assert json.loads(_plan(egress="wireguard").outputs()["runner"]) == "ubuntu-latest"


# ------------------------------------------------------------------- geo check


def test_pais_de_salida() -> None:
    assert geo_check.decide_country({"a": "ES", "b": None}, "ES")[0] == geo_check.OK
    code, detail = geo_check.decide_country({"a": "ES", "b": "US"}, "ES")
    assert code == geo_check.BLOCKED and "US" in detail
    assert geo_check.decide_country({"a": None, "b": None}, "ES")[0] == geo_check.SETUP_ERROR


SITE = geo_check.load_geo_config()["site"]


@pytest.mark.parametrize("probe,expected", [
    (geo_check.SiteProbe(200, "https://www.betsson.es/", "Casino Apuestas Iniciar sesión"), geo_check.OK),
    (geo_check.SiteProbe(451, "https://www.betsson.es/", ""), geo_check.BLOCKED),
    (geo_check.SiteProbe(403, "https://www.betsson.es/", "Forbidden"), geo_check.BLOCKED),
    (geo_check.SiteProbe(200, "https://www.betsson.es/restricted", "Lo sentimos"), geo_check.BLOCKED),
    (geo_check.SiteProbe(200, "https://www.betsson.es/", "Este sitio no está disponible en tu país"), geo_check.BLOCKED),
    (geo_check.SiteProbe(200, "https://www.betsson.es/", "Checking your browser before accessing"), geo_check.BLOCKED),
    (geo_check.SiteProbe(None, "https://www.betsson.es/", ""), geo_check.BLOCKED),
])
def test_clasificacion_del_sitio(probe, expected) -> None:
    assert geo_check.classify_site(probe, SITE)[0] == expected


def test_verificacion_antibot_no_se_salta() -> None:
    _, detail = geo_check.classify_site(geo_check.SiteProbe(200, "https://x/", "Please complete the CAPTCHA"), SITE)
    assert "no se intenta saltar" in detail


# ------------------------------------------------------------------- workflow


def test_desplegables_al_dia() -> None:
    """betsson-es.yml tiene las mismas opciones que el catálogo (python scripts/ci/render_dropdowns.py)."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / WORKFLOW.name
        shutil.copyfile(WORKFLOW, copy)
        assert not render_workflow(load_catalog("es"), copy), "Ejecuta: python scripts/ci/render_dropdowns.py"
