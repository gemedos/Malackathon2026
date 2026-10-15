# Comandos locales (sin Docker). Requiere Python 3.10+ y Tesseract (brew install tesseract tesseract-lang).
PYTHON ?= python3
PY := .venv/bin/python

.PHONY: setup check test demo clean

setup:  ## Crea el entorno .venv e instala las dependencias Python
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -r requirements.txt

check:  ## Comprueba que Tesseract y los idiomas eng/spa están instalados
	@tesseract --version | head -1
	@tesseract --list-langs | grep -qx eng && tesseract --list-langs | grep -qx spa && echo "Idiomas eng y spa: OK"

test:   ## Pruebas automáticas (sintéticas, no necesitan Tesseract)
	$(PY) -m unittest discover -s tests -v

demo:   ## Genera la demo sintética T01-T04 y ejecuta la matriz con OCR real
	$(PY) scripts/make_demo.py demo
	$(PY) offline.py matrix --plan demo/plan.json --out reports/demo

clean:  ## Borra demo, informes y evidencias generadas
	rm -rf demo reports evidence
