"""Calibración de un juego en dos pasos.

1) Capturas reales del juego (abre betsson.es, login, juego en Real Play; NO hace ningún spin):

    python scripts/calibrate.py capture --provider "Pragmatic Play" --game "Sweet Bonanza" [--headed]

   Guarda calibration/<proveedor>/<juego>/frame-XX.png y crea config/games/<proveedor>/<juego>.yaml
   (esqueleto con calibrated: false) si no existe.

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
                    for index in range(args.frames):
                        frame = driver.capture()
                        size = (frame.shape[1], frame.shape[0])
                        cv2.imwrite(str(out / f"frame-{index:02d}.png"), frame)
                        driver.wait(args.interval * 1000)
        finally:
            browser.close()
    print(f"{args.frames} capturas {size[0]}x{size[1]} en {out.relative_to(ROOT)}")
    yaml_path = calibration_path(args.provider, args.game)
    if not yaml_path.exists():
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(skeleton(args.provider, args.game, size), encoding="utf-8")
        print(f"Esqueleto creado: {yaml_path.relative_to(ROOT)} (ajusta regiones y recorta spin.png)")
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
    for name in ("capture", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("--provider", required=True)
        sub.add_argument("--game", required=True)
    cap = commands.choices["capture"]
    cap.add_argument("--account", default="FUNDED")
    cap.add_argument("--frames", type=int, default=6)
    cap.add_argument("--interval", type=float, default=1.0, help="segundos entre capturas")
    cap.add_argument("--headed", action="store_true")
    commands.choices["check"].add_argument("--image", required=True)
    args = parser.parse_args()
    return capture(args) if args.command == "capture" else check(args)


if __name__ == "__main__":
    sys.exit(main())
