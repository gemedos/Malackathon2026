# Módulo de visión — Malackathon 2026

Parte de **visión** del proyecto (ver `../CLAUDE.md`): recibe capturas del juego y decide, solo con lo que ve el jugador, si cada escenario es PASS, FAIL o INCONCLUSIVE. **No** abre el navegador, no hace login ni clics: eso lo hace la parte Playwright, que le pasa las capturas.

```
Playwright (otro equipo) ──capturas──▶  este módulo  ──▶  reports/report.txt  (formato RR-03, T01–T04)
```

## Puesta en marcha (local, macOS)

```sh
brew install tesseract tesseract-lang   # motor OCR + idiomas (una sola vez)
make setup                              # crea .venv e instala OpenCV, NumPy, pytesseract
make check                              # comprueba Tesseract con inglés y español
make test                               # 68 pruebas automáticas → debe terminar en "OK"
make demo                               # demo completa T01–T04 con OCR real → "OVERALL: PASS"
```

`make demo` dibuja capturas **sintéticas** (no son de Betsson) para que veas el flujo completo funcionando; el informe queda en `reports/demo/report.txt` y las evidencias (recortes de cada lectura) en `reports/demo/T01/`, etc.

Sin `make`: `.venv/bin/python -m unittest discover -s tests -v` y `.venv/bin/python offline.py matrix --plan demo/plan.json`.

## Qué es cada cosa

| Ruta | Para qué sirve |
|---|---|
| `offline.py` | Programa principal (línea de comandos): `inspect`, `scenario`, `matrix` |
| `config/markets.json` | Datos de cada mercado: idioma, moneda, frases de "saldo insuficiente". Cambiar mercado = editar este JSON, no el código |
| `config/profiles/*.example.json` | Calibración de un juego: dónde está cada cosa en la captura. Las coordenadas son **de ejemplo** |
| `scripts/make_demo.py` | Genera la demo sintética |
| `tests/` | Pruebas automáticas de la lógica |
| `Makefile` | Atajos `setup`, `check`, `test`, `demo`, `clean` |
| `vision_engine/` | El código del módulo (tabla siguiente) |

| `vision_engine/` | Responsabilidad |
|---|---|
| `engine.py` | Punto de entrada: localizar Spin, leer HUD, mensaje y saldo Betsson |
| `scenario.py` | Graba un intento: frames antes → **un** clic → frames después |
| `evaluation.py` | Validaciones de SC-01 (giro completado) y SC-02 (saldo insuficiente) |
| `report.py` | Matriz T01–T04 e informe de texto RR-03 |
| `profile.py` | Carga y valida el perfil y `config/markets.json` |
| `matching.py` / `ready.py` | Encontrar el botón Spin / saber si está activo |
| `motion.py` | Detectar que los rodillos empiezan a moverse y se paran |
| `ocr.py` | Leer texto de cada zona y guardar los recortes como evidencia |
| `consensus.py` | Aceptar una lectura solo si se repite igual en ≥ 3 frames |
| `money.py` / `currency.py` / `language.py` / `messages.py` | Importes con `Decimal`, moneda, idioma del mensaje, frases de rechazo |
| `geometry.py` / `imaging.py` / `evidence.py` / `verdict.py` / `errors.py` | Utilidades: coordenadas, imágenes, guardado, resultados, errores |

## Qué valida (según `../CLAUDE.md`)

**SC-01 Completed Real Play Spin**: botón Spin localizado y juego listo · saldo inicial, apuesta y moneda leídos (≥ 3 lecturas iguales) · el giro empieza y termina (movimiento → reposo + botón listo) · premio leído de su zona (nunca deducido) · la apuesta no cambia · `saldo final = inicial − apuesta + premio` en el juego **y** en Betsson.

**SC-02 Insufficient Balance**: mensaje de saldo insuficiente en ≥ 3 frames · en el idioma del mercado (inglés en .com, español en .pe) · moneda correcta · saldo del juego sin cambios durante la ventana · ningún giro pagado · saldo Betsson sin cambios.

Resultados: **PASS** solo con todas las pruebas; **FAIL** si se demuestra un error (p. ej. el saldo no cuadra); **INCONCLUSIVE** si algo no se pudo verificar (OCR ilegible, timeout, perfil sin calibrar); **ERROR** si falló la ejecución (imagen inexistente, Tesseract ausente). Código de salida: 0 PASS · 1 FAIL · 2 INCONCLUSIVE · 3 ERROR.

## Usarlo con capturas reales

1. **Calibrar** (una vez por juego y mercado): copiar `config/profiles/com.example.json` y ajustar `image_size` y cada región `[x, y, ancho, alto]` mirando una captura real. Recortar el botón Spin de esa captura → `assets/spin.png`. Comprobar con:
   ```sh
   .venv/bin/python offline.py inspect --profile config/profiles/com.json --template assets/spin.png --image assets/captura.png
   ```
   y revisar los recortes en `reports/inspect/`. Cuando lea bien, poner `"calibrated": true`.
2. **Secuencia** de cada intento (la entrega Playwright), un JSON con los frames cada ~200 ms:
   ```json
   {"click_timestamp": 1.2,
    "frames": [{"file": "f00.png", "timestamp": 0.0}, {"file": "f01.png", "timestamp": 0.5}, "..."]}
   ```
   Al menos 3 frames antes del clic y suficientes después para ver el giro terminado (o la ventana de rechazo).
3. **Plan** con las 4 combinaciones (rutas relativas al plan; ver `demo/plan.json` tras `make demo`):
   ```json
   {"tests": [
     {"profile": "config/profiles/com.json", "scenario": "spin", "template": "assets/spin.png",
      "sequence": "capturas/T01/sequence.json", "betsson": {"before": "10.00", "after": "14.00"}},
     "... T02, T03, T04 ..."]}
   ```
   El saldo Betsson puede darse como valores o como capturas de la página (`"before": [{"file": "p0.png", "timestamp": 0.0}, ...]`), que se leen por OCR en la región `betsson_page` del perfil.
4. Ejecutar `.venv/bin/python offline.py matrix --plan plan.json` → `reports/report.txt` y `reports/report.json`.

## Integración en vivo con Playwright

```python
import time
from vision_engine import (GameProfile, VisionEngine, SpinAttemptRecorder, BetssonBalance,
                           decode_png, load_template, page_point, evaluate_spin)

profile = GameProfile.load('config/profiles/com.json')
recorder = SpinAttemptRecorder(VisionEngine(profile, 'reports/T01'), load_template('assets/spin.png'))
capture = lambda: decode_png(page.screenshot(clip=game_box, scale='css'))   # caja del iframe

for _ in range(3):                                  # frames ANTES del clic
    recorder.observe_before(capture(), time.monotonic()); page.wait_for_timeout(350)
hit = recorder.register_click(time.monotonic())     # lanza error si no ve el Spin: no clicar
page.mouse.click(*page_point(hit.point, profile.image_size, game_box))   # un único intento
# ... recorder.observe_after(capture(), time.monotonic()) cada ~200 ms hasta reposo o timeout ...
report = evaluate_spin(recorder.record(), BetssonBalance.from_values(before, after))
```

## Limitaciones conocidas

- Los perfiles de `config/profiles/` y la demo **no** están calibrados para Betsson: hace falta calibrar con capturas reales de cada juego y mercado.
- Las frases de `config/markets.json` son un punto de partida; el reto no fija el texto exacto, así que hay que ajustarlas al mensaje real.
- Bonus y cascadas se detectan como INCONCLUSIVE; requieren adaptación por juego.
- La detección de idioma es una heurística de palabras frecuentes (inglés/español).
