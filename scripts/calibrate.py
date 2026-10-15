"""Calibración de un juego en dos pasos.

1) Capturas reales del juego (abre betsson.es, login, juego en Real Play; NO hace ningún spin):

    python scripts/calibrate.py capture --provider "Pragmatic Play" --game "Sweet Bonanza" [--headed]

   Guarda calibration/<proveedor>/<juego>/frame-XX.png y crea config/games/<proveedor>/<juego>.yaml
   (esqueleto con calibrated: false) si no existe.

0) Automático (lo habitual): captura el juego SIN apostar, localiza las etiquetas CRÉDITO/APUESTA/GANANCIA,
   verifica que en cada región propuesta se lee un importe y escribe el YAML del juego:

    python run.py calibrate "NetEnt" "Dead West"

2) Comprobar regiones y plantilla sobre una captura (sin navegador):

    python scripts/calibrate.py check --provider "Pragmatic Play" --game "Sweet Bonanza" --image calibration/.../frame-00.png

   Imprime lo que lee cada región y guarda una imagen anotada en calibration/<proveedor>/<juego>/check/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vision-module")]

import cv2  # noqa: E402

from validator.config import current_market, load_market, load_selectors  # noqa: E402
from validator.game.calibration import build_profile, calibration_path, load_calibration, skeleton  # noqa: E402
from validator.urls import slugify  # noqa: E402
from vision_engine import ReadyDetector, VisionEngine, load_image  # noqa: E402
from vision_engine.annotate import annotate  # noqa: E402
from vision_engine.errors import ImageError  # noqa: E402

CALIBRATION_DIR = ROOT / "calibration"   # capturas locales (en .gitignore)


def capture(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    from validator.browser import launch_browser
    from validator.evidence import Evidence
    from validator.game.driver import GameDriver
    from validator.navigation import CHECK_LOGIN, GAME_CHECKS, login, open_game, work_context
    from validator.results import Checklist, Results
    from validator.secrets import load_env_file

    load_env_file()
    market = load_market(current_market())
    selectors = load_selectors(market.market)
    evidence = Evidence(market.market, "calibracion")
    checklist = Checklist(Results(evidence.path("calibration_results.json")), "calibracion", market.market,
                          args.provider, args.game, (CHECK_LOGIN, *GAME_CHECKS))
    out = CALIBRATION_DIR / slugify(args.provider) / slugify(args.game)
    out.mkdir(parents=True, exist_ok=True)
    size = None
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=not args.headed)
        try:
            state = login(browser, market, selectors, evidence, provider=args.provider, account=args.account,
                          check=checklist.check)
            with work_context(browser, market, evidence, state) as context:
                with open_game(context, market, selectors, evidence.for_game(args.provider, args.game),
                               provider=args.provider, game=args.game, check=checklist.check) as session:
                    driver = GameDriver(session)
                    hud_seen, start_clicks = False, 0
                    for index in range(args.frames):
                        frame = driver.capture()
                        size = (frame.shape[1], frame.shape[0])
                        cv2.imwrite(str(out / f"frame-{index:02d}.png"), frame)
                        if getattr(args, "no_skeleton", False) and not hud_seen:
                            # Modo automático: si el juego tiene pantalla de inicio («CONTINUAR»...), se pulsa
                            # (aún no hay HUD, así que no se puede apostar) hasta ver el HUD.
                            from vision_engine.hud_locator import find_start_button, locate_hud
                            if {"balance", "wager"} <= set(locate_hud(frame, "spa+eng").verified):
                                hud_seen = True
                            elif start_clicks < 4:
                                point = find_start_button(frame, "spa+eng")
                                if point is not None:
                                    print(f"Pantalla de inicio: pulsando el botón en {point}")
                                    driver.click(point, size)
                                    start_clicks += 1
                                    driver.wait(3000)
                        driver.wait(args.interval * 1000)
        finally:
            browser.close()
    print(f"{args.frames} capturas {size[0]}x{size[1]} en {out.relative_to(ROOT)}")
    yaml_path = calibration_path(args.provider, args.game)
    if getattr(args, "no_skeleton", False):
        return 0
    if not yaml_path.exists():
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(skeleton(args.provider, args.game, size), encoding="utf-8")
        print(f"Esqueleto creado: {yaml_path.relative_to(ROOT)} (ajusta regiones y recorta spin.png)")
    return 0


def auto(args: argparse.Namespace) -> int:
    """Captura + propuesta automática de regiones. Escribe config/games/<proveedor>/<juego>.yaml (calibrated: false)."""
    import shutil

    from vision_engine.hud_locator import HudProposal, locate_hud

    args.no_skeleton = True
    if not getattr(args, "reuse", False):          # --reuse: reutiliza las capturas ya hechas (sin abrir el navegador)
        capture(args)
    out = CALIBRATION_DIR / slugify(args.provider) / slugify(args.game)
    frames = sorted(out.glob("frame-*.png"))
    best: tuple[HudProposal, Path] | None = None
    for path in reversed(frames):            # los últimos fotogramas: el juego ya ha terminado de cargar
        image = cv2.imread(str(path))
        proposal = locate_hud(image, "spa+eng")
        print(f"{path.name}: etiquetas verificadas {sorted(proposal.verified) or 'ninguna'}")
        if best is None or proposal.score > best[0].score:
            best = (proposal, path)
        if {"balance", "wager"} <= set(proposal.verified):
            break
    proposal, frame_path = best
    image = cv2.imread(str(frame_path))
    height, width = image.shape[:2]
    print("\n".join(["", *proposal.notes]))
    if not {"balance", "wager"} <= set(proposal.regions):
        print(f"\nNO se localizó el HUD. Mira las capturas en {out.relative_to(ROOT)}: si el juego muestra una pantalla "
              "de inicio (hay que pulsar «jugar»), o el HUD usa otras palabras, añade las etiquetas en "
              "vision-module/vision_engine/hud_locator.py (LABELS / LABEL_WORDS) o calibra a mano "
              "(scripts/calibrate.py check).")
        return 1
    # Pista del botón Spin: círculos numerados sobre la captura; el nº 1 se guarda como plantilla provisional.
    from vision_engine.hud_locator import find_spin_candidates
    from vision_engine.geometry import ROI
    candidates = find_spin_candidates(image)
    slug = slugify(args.game)
    yaml_path = calibration_path(args.provider, args.game)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    spin_name = f"{slug}-spin.png"
    shown = image.copy()
    for number, (x, y, w, h) in enumerate(candidates, 1):
        cv2.rectangle(shown, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cv2.putText(shown, str(number), (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imwrite(str(out / f"spin-candidato-{number}.png"), image[y:y + h, x:x + w])
    regions = {name: ROI(int(v[0] * width), int(v[1] * height), int(v[2] * width), int(v[3] * height))
               for name, v in proposal.regions.items()}
    cv2.imwrite(str(out / "annotated-auto.png"), annotate(shown, regions, proposal.verified))
    lines = {name: "[" + ", ".join(str(v) for v in values) + "]" for name, values in proposal.regions.items()}
    if yaml_path.exists():
        backup = yaml_path.with_suffix(".yaml.bak")
        shutil.copy(yaml_path, backup)
        print(f"Ya existía {yaml_path.name}: copia en {backup.name}")
    from validator.game.autocal import write_calibration
    write_calibration(args.provider, args.game, image, proposal, calibrated=False)
    print(f"\nEscrito {yaml_path.relative_to(ROOT)} (calibrated: false)")
    print(f"Revisa {(out / 'annotated-auto.png').relative_to(ROOT)}; si el Spin correcto no es el nº 1, copia "
          f"calibration/.../spin-candidato-N.png sobre config/games/{slugify(args.provider)}/{spin_name}.")
    print("Si todo está bien: pon calibrated: true y ejecuta  python run.py \"%s\" \"%s\"" % (args.provider, args.game))
    return 0


def check(args: argparse.Namespace) -> int:
    market = load_market(current_market())
    loaded = load_calibration(args.provider, args.game)
    image = load_image(args.image)
    profile = build_profile(loaded.calibration, market, (image.shape[1], image.shape[0]))
    out = CALIBRATION_DIR / slugify(args.provider) / slugify(args.game) / "check"
    engine = VisionEngine(profile, out)

    labels: dict[str, str] = {}
    try:
        spin, busy = loaded.templates()
        hit = engine.locate_spin(image, spin)
        ready = ReadyDetector(profile, spin, busy).observe(image)
        labels["spin_search"] = (f"Spin {hit.confidence:.2f}" if hit else "Spin NO encontrado") + \
            (" listo" if ready.ready else " no listo")
        print(f"Spin: {hit.to_dict() if hit else 'no encontrado (umbral ' + str(profile.template_threshold) + ')'}")
        print(f"Control listo: {ready.ready} ({ready.reason}; confianza {ready.confidence})")
    except ImageError as exc:
        print(f"Plantilla: {exc}")
    readings = {**engine.read_hud(image, "check"), "message": engine.read_message(image, "check")}
    for name, reading in readings.items():
        shown = reading.value or reading.error or ""
        labels[name] = reading.value or "ilegible"
        print(f"{name:9} texto={reading.raw_text!r:32} -> {shown}")
    print(f"Frase de saldo insuficiente detectada: {engine.is_insufficient_message(readings['message'].raw_text)}")
    annotated = out / "annotated.png"
    cv2.imwrite(str(annotated), annotate(image, profile.regions, labels))
    print(f"Imagen anotada: {annotated.relative_to(ROOT)}  (recortes de cada región en {out.relative_to(ROOT)})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibración visual de un juego")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "check", "auto"):
        sub = commands.add_parser(name)
        sub.add_argument("--provider", required=True)
        sub.add_argument("--game", required=True)
    cap = commands.choices["capture"]
    for extra in ("auto",):
        sub = commands.choices[extra]
        sub.add_argument("--account", default="FUNDED")
        sub.add_argument("--frames", type=int, default=10)
        sub.add_argument("--interval", type=float, default=2.0)
        sub.add_argument("--headed", action="store_true", default=True)
        sub.add_argument("--reuse", action="store_true", help="analizar las capturas existentes, sin navegador")
    cap.add_argument("--account", default="FUNDED")
    cap.add_argument("--frames", type=int, default=6)
    cap.add_argument("--interval", type=float, default=1.0, help="segundos entre capturas")
    cap.add_argument("--headed", action="store_true")
    commands.choices["check"].add_argument("--image", required=True)
    args = parser.parse_args()
    return {"capture": capture, "check": check, "auto": auto}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
