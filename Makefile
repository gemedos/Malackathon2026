# Flujo completo en local. Requiere Python 3.11+ y Tesseract (macOS: brew install tesseract tesseract-lang).
# Uso: make <objetivo> [PROVIDER="Pragmatic Play"] [GAME="Sweet Bonanza"] [IMAGE=ruta.png]
PYTHON ?= python3
PY := .venv/bin/python
PROVIDER ?= Pragmatic Play
GAME ?= Sweet Bonanza

.PHONY: setup check test navigation calibrate calibrate-check scenarios report clean

setup:            ## Entorno .venv con dependencias y Chromium de Playwright
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -r requirements.txt
	$(PY) -m playwright install chromium

check:            ## Tesseract con español e inglés
	@tesseract --version | head -1
	@tesseract --list-langs | grep -qx spa && tesseract --list-langs | grep -qx eng && echo "Idiomas spa y eng: OK"

test:             ## Pruebas SIN dinero real ni betsson.es (visión, integración y juego falso en Chromium)
	$(PY) -m pytest vision-module/tests tests/test_integration_units.py tests/test_game_flow_offline.py

navigation:       ## Login + abrir el juego en Real Play (sin spins). Necesita .env
	$(PY) -m pytest tests/test_navigation.py --provider "$(PROVIDER)" --game "$(GAME)"

calibrate:        ## Capturas reales del juego + esqueleto config/games/... (sin spins). Necesita .env
	$(PY) scripts/calibrate.py capture --provider "$(PROVIDER)" --game "$(GAME)"

calibrate-check:  ## Comprueba la calibración sobre una captura: make calibrate-check IMAGE=calibration/...png
	$(PY) scripts/calibrate.py check --provider "$(PROVIDER)" --game "$(GAME)" --image "$(IMAGE)"

scenarios:        ## Escenarios 1 y 2 con DINERO REAL (cuentas FUNDED y EMPTY de .env) + informe
	-$(PY) -m pytest tests/test_game_scenarios.py -m real_money --provider "$(PROVIDER)" --game "$(GAME)"
	$(PY) scripts/report.py
	$(PY) -m pytest tests/test_secret_hygiene.py

report:           ## Regenera artifacts/es/report.{txt,html} desde results.json
	$(PY) scripts/report.py

clean:            ## Borra artifacts, sesión y capturas de calibración locales
	rm -rf artifacts .auth calibration
