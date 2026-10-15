#!/usr/bin/env python3
"""Punto de entrada único. Sin argumentos ejecuta la prueba completa de Bubble Up (Pragmatic Play).

    python run.py setup                      # 1ª vez: dependencias, Chromium, OCR en español y credenciales
    python run.py                            # escenarios 1 y 2 de Bubble Up, navegador visible, con informe
    python run.py "Pragmatic Play" "Gates of Olympus"      # otro juego (necesita calibración, ver HOW_TO_RUN.md)
    python run.py -s 1                       # solo el escenario 1 (cuenta con saldo)
    python run.py -s 2                       # solo el escenario 2 (cuenta sin saldo)
    python run.py test                       # pruebas SIN dinero real ni betsson.es
    python run.py calibrate "<proveedor>" "<juego>"  # juego NUEVO: localiza el HUD solo y escribe su YAML
    python run.py inspect [proveedor] [juego]  # abre el juego SIN apostar y lista diálogos/botones visibles
    python run.py clean                      # borra evidencias locales (artifacts/ y .auth/)

Los escenarios 1 y 2 juegan con dinero real en betsson.es (una apuesta por escenario).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
ENV_FILE = ROOT / ".env"
TESSDATA = ROOT / "tessdata"
SPA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata"
CREDENTIALS = {
    "FUNDED": ("BETSSON_ES_FUNDED_USER", "BETSSON_ES_FUNDED_PASS", "cuenta CON saldo (escenario 1)"),
    "EMPTY": ("BETSSON_ES_EMPTY_USER", "BETSSON_ES_EMPTY_PASS", "cuenta SIN saldo (escenario 2)"),
}
SCENARIOS = {"1": ("escenario1", ["FUNDED"]), "2": ("escenario2", ["EMPTY"]), "all": (None, ["FUNDED", "EMPTY"])}


# ---------------------------------------------------------------------------------------------- .env

def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    values = read_env()
    values.update(updates)
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")


# ---------------------------------------------------------------------------------------------- comprobaciones

def tesseract_exe() -> str | None:
    found = os.environ.get("TESSERACT_CMD") or read_env().get("TESSERACT_CMD") or shutil.which("tesseract")
    if found:
        return found
    for candidate in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                      str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe")):
        if Path(candidate).exists():
            return candidate
    return None


def languages(exe: str) -> set[str]:
    env = dict(os.environ, TESSDATA_PREFIX=read_env().get("TESSDATA_PREFIX", os.environ.get("TESSDATA_PREFIX", "")))
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, env=env)
    return set(out.stdout.split()[1:])


def problems(accounts: list[str]) -> list[str]:
    found: list[str] = []
    for module in ("playwright", "pytest", "yaml", "pydantic", "cv2", "pytesseract", "numpy", "dotenv"):
        try:
            __import__(module)
        except ImportError:
            found.append(f"falta el paquete Python '{module}' -> python -m pip install -r requirements.txt")
            break
    exe = tesseract_exe()
    if exe is None:
        found.append("Tesseract no está instalado (ver HOW_TO_RUN.md, paso 2)")
    elif not {"spa", "eng"} <= languages(exe):
        found.append("Tesseract no tiene el idioma español -> python run.py setup")
    env = read_env()
    for account in accounts:
        user, password, label = CREDENTIALS[account]
        if not env.get(user) or not env.get(password):
            found.append(f"faltan las credenciales de la {label} en .env -> python run.py setup")
    return found


# ---------------------------------------------------------------------------------------------- comandos

def cmd_setup(_: argparse.Namespace) -> int:
    print("1/4 Dependencias de Python")
    subprocess.run([PY, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)
    print("2/4 Chromium de Playwright")
    subprocess.run([PY, "-m", "playwright", "install", "chromium"], check=True)
    print("3/4 OCR (Tesseract + español)")
    exe = tesseract_exe()
    if exe is None:
        print("   ERROR: instala Tesseract primero (Windows: https://github.com/UB-Mannheim/tesseract/wiki; "
              "macOS: brew install tesseract; Linux: apt install tesseract-ocr). Después repite 'python run.py setup'.")
        return 1
    TESSDATA.mkdir(exist_ok=True)
    for lang in ("spa", "eng"):
        target = TESSDATA / f"{lang}.traineddata"
        if not target.exists():
            print(f"   descargando {lang}.traineddata ...")
            urllib.request.urlretrieve(SPA_URL.format(lang=lang), target)
    write_env({"TESSDATA_PREFIX": str(TESSDATA)})
    print("   idiomas disponibles:", ", ".join(sorted(languages(exe))))
    print("4/4 Credenciales (se guardan solo en .env, que no se sube a git)")
    env = read_env()
    updates = {}
    for user, password, label in CREDENTIALS.values():
        if env.get(user) and env.get(password):
            print(f"   {label}: ya configurada")
            continue
        updates[user] = input(f"   Usuario/email de la {label}: ").strip()
        updates[password] = getpass.getpass("   Contraseña (no se muestra): ")
    if updates:
        write_env(updates)
    left = problems(["FUNDED", "EMPTY"])
    print("\nTodo listo. Ejecuta: python run.py" if not left else "\nPendiente:\n - " + "\n - ".join(left))
    return 0 if not left else 1


def cmd_test(_: argparse.Namespace) -> int:
    env = dict(os.environ, PROVIDER="Pragmatic Play", GAME="Bubble Up")
    return subprocess.call([PY, "-m", "pytest", "vision-module/tests", "tests", "-p", "no:cacheprovider", "-q",
                            "--ignore=tests/test_game_scenarios.py", "--ignore=tests/test_navigation.py"],
                           cwd=ROOT, env=env)


def cmd_inspect(_: argparse.Namespace) -> int:
    return subprocess.call([PY, "scripts/inspect_game.py", *sys.argv[2:]], cwd=ROOT)


def cmd_calibrate(_: argparse.Namespace) -> int:
    rest = sys.argv[2:]
    if len(rest) < 2:
        print('Uso: python run.py calibrate "<proveedor>" "<juego>"')
        return 2
    return subprocess.call([PY, "scripts/calibrate.py", "auto", "--provider", rest[0], "--game", rest[1], *rest[2:]], cwd=ROOT)


def cmd_clean(_: argparse.Namespace) -> int:
    for name in ("artifacts", ".auth"):
        shutil.rmtree(ROOT / name, ignore_errors=True)
    print("Borrados artifacts/ y .auth/")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    key, accounts = SCENARIOS[args.scenario]
    found = problems(accounts)
    if found:
        print("No se puede empezar:\n - " + "\n - ".join(found))
        return 2
    if not args.keep:
        shutil.rmtree(ROOT / "artifacts" / "es", ignore_errors=True)   # evidencias del run anterior
    command = [PY, "-m", "pytest", "tests/test_game_scenarios.py", "-m", "real_money", "-p", "no:cacheprovider",
               "--provider", args.provider, "--game", args.game]
    if not args.headless:
        command.append("--headed")
    if key:
        command += ["-k", key]
    print(f"\n>>> {args.provider} / {args.game} — escenarios: {args.scenario} — DINERO REAL\n")
    code = subprocess.call(command, cwd=ROOT)
    subprocess.call([PY, "scripts/make_report.py"], cwd=ROOT, stdout=subprocess.DEVNULL,
                    env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    summary()
    clean = subprocess.call([PY, "-m", "pytest", "tests/test_secret_hygiene.py", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                            env=dict(os.environ, PROVIDER=args.provider, GAME=args.game), stdout=subprocess.DEVNULL) == 0
    print("Higiene de secretos: " + ("OK, no hay credenciales en artifacts/" if clean else
          "¡HAY credenciales en artifacts/! No compartas esa carpeta (python run.py clean)"))
    return code or (0 if clean else 1)


def summary() -> None:
    path = ROOT / "artifacts" / "es" / "results.json"
    if not path.exists():
        return
    rows = json.loads(path.read_text(encoding="utf-8"))
    print("\n" + "=" * 70 + "\nRESUMEN")
    for scenario in dict.fromkeys(r["scenario"] for r in rows):
        mine = [r for r in rows if r["scenario"] == scenario]
        counts = {s: sum(1 for r in mine if r["status"] == s) for s in ("pass", "fail", "inconclusive", "error")}
        bad = [r for r in mine if r["status"] != "pass"]
        verdict = "ERROR" if counts["error"] else "FAIL" if counts["fail"] else "INCONCLUSIVE" if counts["inconclusive"] else "PASS"
        print(f"\n[{verdict}] {scenario}: " + ", ".join(f"{n} {s}" for s, n in counts.items() if n))
        for r in bad:
            print(f"   - {r['check']}: {r['status']} — {r['detail']}")
    print("\nInforme: artifacts/es/report.html (y report.txt)   Vídeo y capturas: artifacts/es/<proveedor>/<juego>/")


def main() -> int:
    commands = {"setup": cmd_setup, "test": cmd_test, "clean": cmd_clean, "inspect": cmd_inspect, "calibrate": cmd_calibrate}
    if len(sys.argv) > 1 and sys.argv[1] in commands:
        return commands[sys.argv[1]](argparse.Namespace())
    parser = argparse.ArgumentParser(
        description="Validador de juegos de Betsson (visión por pantalla). Otros comandos: setup | test | inspect | calibrate | clean.")
    parser.add_argument("provider", nargs="?", default="Pragmatic Play")
    parser.add_argument("game", nargs="?", default="Bubble Up")
    parser.add_argument("-s", "--scenario", choices=list(SCENARIOS), default="all",
                        help="1 = con saldo, 2 = sin saldo, all = ambos (por defecto)")
    parser.add_argument("--headless", action="store_true", help="sin ventana (por defecto se ve el navegador)")
    parser.add_argument("--keep", action="store_true", help="no borrar las evidencias del run anterior")
    return cmd_run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
