# Módulo independiente: visión del iframe

Entrega para el equipo OpenCV + OCR. El navegador, el login y los clics los gestiona el equipo Playwright. Este motor solo observa imágenes del rectángulo visible del juego; no inspecciona el interior del iframe (ni DOM, ni canvas API, ni red).

## Estructura

```
vision-module/
├── offline.py                 # CLI: analiza capturas ya tomadas (inspect / scenario)
├── profile.example.json       # perfil ILUSTRATIVO betsson.com (EUR) — no calibrado
├── profile.example.pe.json    # perfil ILUSTRATIVO betsson.pe (PEN) — no calibrado
├── vision_engine/
│   ├── errors.py      # errores explícitos (ProfileError, CalibrationError, SequenceError...)
│   ├── profile.py     # GameProfile: carga y valida el perfil + ajustes de movimiento/consenso/listo
│   ├── geometry.py    # ROI y page_point (imagen → CSS con offset y escala)
│   ├── imaging.py     # decodificación PNG y preprocesado para OCR
│   ├── matching.py    # localización multi-escala de plantillas (botón Spin)
│   ├── ocr.py         # OCR por campo con evidencias (crop original + preprocesado)
│   ├── money.py       # parse_money (Decimal estricto) y reconcile
│   ├── currency.py    # detección explícita de moneda (EUR/€, PEN/S/...)
│   ├── messages.py    # frases de saldo insuficiente; rechaza patrones genéricos
│   ├── motion.py      # MotionTracker: movimiento → reposo, timeout, reanudación
│   ├── ready.py       # ReadyDetector: control Spin habilitado visible
│   ├── consensus.py   # consenso de >= 3 lecturas en frames distintos y separados
│   ├── engine.py      # VisionEngine: fachada (check_size, locate_spin, read_hud...)
│   ├── scenario.py    # SpinAttemptRecorder: un único intento antes/clic/después
│   ├── evaluation.py  # evaluate_spin / evaluate_insufficient → PASS/FAIL/INCONCLUSIVE
│   └── verdict.py     # Verdict, AssertionResult, ScenarioReport
└── tests/             # pruebas SINTÉTICAS de lógica (no prueban compatibilidad con Betsson)
```

Flujo de datos: `frame BGR → VisionEngine (Spin, OCR por campo) → SpinAttemptRecorder (antes · clic único · después, con MotionTracker y ReadyDetector) → ScenarioRecord → evaluate_* → ScenarioReport`.

## Ejecutar con Docker (recomendado)

Con Docker Desktop iniciado, en esta carpeta:

```sh
docker compose build             # imagen con OpenCV, NumPy, Tesseract (eng + spa)
docker compose run --rm vision   # ejecuta las pruebas automáticas
```

El contenedor de ejecución no tiene red y no incluye navegador. Las evidencias quedan en la carpeta local gracias al volumen compartido.

### Instalación local sin Docker

Python 3.10+: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`. Instalar Tesseract con inglés y español (`brew install tesseract tesseract-lang` o `apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa`) y verificar con `tesseract --list-langs`.

## Calibrar un juego

1. Obtener capturas autorizadas del rectángulo completo de UN juego, sin redimensionar.
2. Recortar el botón Spin habilitado → `assets/spin.png`. Opcional pero recomendado: el botón en estado ocupado/deshabilitado → `assets/spin_busy.png`. No se incluyen plantillas inventadas.
3. Copiar `profile.example.json` (o `.pe.json`) a `profile.json` y ajustar `image_size` y cada región en píxeles LOCALES. Balance, apuesta, premio, moneda, rodillos y mensaje deben ir en regiones separadas.
4. Ajustar `decimal_separator` a lo observado (no al dominio), `ocr_language` y `insufficient_patterns` al texto real (en minúsculas y sin tildes; se rechazan patrones genéricos como `saldo` o `balance`).
5. Ajustar umbrales con clips etiquetados: `motion` (movimiento ≠ reposo; nunca cero), `consensus` (mínimo 3 lecturas), `ready`, `insufficient_window_seconds`.
6. Solo tras validar con capturas reales, poner `"calibrated": true`. Con `false` ningún escenario puede salir PASS.

## Runner offline

```sh
# Captura aislada: Spin, control listo, OCR por campo. Siempre INCONCLUSIVE.
docker compose run --rm vision python offline.py inspect \
  --profile profile.json --template assets/spin.png --image assets/before.png --out evidence

# Secuencia de un único intento
docker compose run --rm vision python offline.py scenario --kind spin \
  --profile profile.json --template assets/spin.png --busy-template assets/spin_busy.png \
  --sequence assets/sequence.json --out evidence \
  --external-before 10.00 --external-after 14.00     # opcional: lo aporta Playwright
```

`--kind insufficient` evalúa el escenario de saldo insuficiente. Formato de `sequence.json` (rutas relativas al JSON, tiempos crecientes en segundos, frames cada ~150–250 ms):

```json
{"click_timestamp": 1.2,
 "frames": [{"file": "f0.png", "timestamp": 0.0}, {"file": "f1.png", "timestamp": 0.5}, {"file": "f2.png", "timestamp": 1.0},
            {"file": "f3.png", "timestamp": 1.4}, "..."]}
```

Se requieren ≥ 3 frames antes del clic (consenso del balance inicial) y ≥ 3 frames en reposo con control listo después. Se guardan frames, crops originales y preprocesados, y `scenario.json` / `observations.json`. Código de salida: `0` PASS, `1` FAIL, `2` INCONCLUSIVE, `3` error de entrada o calibración.

## Contrato con el equipo Playwright

Entrada: captura PNG del rectángulo visible del iframe, caja CSS del mismo rectángulo, mercado y tiempos monotónicos. Salida: coordenadas LOCALES con confianza, OCR por campo, estados de movimiento/control listo, errores explícitos y veredictos por aserción.

Ejemplo de integración síncrona (código del equipo navegador; Playwright no es dependencia de este módulo):

```python
import time
from vision_engine import (GameProfile, VisionEngine, SpinAttemptRecorder, MotionState,
                           ExternalBalance, decode_png, load_template, page_point, evaluate_spin)

profile = GameProfile.load('profile.json')
engine = VisionEngine(profile, 'evidence')
recorder = SpinAttemptRecorder(engine, load_template('assets/spin.png'), load_template('assets/spin_busy.png'))

def capture():   # game_box: caja del iframe EXTERIOR; mismo rectángulo que la captura
    return decode_png(page.screenshot(clip=game_box, scale='css'))

for _ in range(3):                       # frames ANTES del clic, separados
    recorder.observe_before(capture(), time.monotonic())
    page.wait_for_timeout(350)

hit = recorder.register_click(time.monotonic())   # lanza SpinNotFoundError si falta evidencia
frame_size = (profile.image_size[0], profile.image_size[1])
page.mouse.click(*page_point(hit.point, frame_size, game_box))   # exactamente un intento

settled = 0
while True:
    page.wait_for_timeout(200)
    frame = recorder.observe_after(capture(), time.monotonic())
    if frame.motion.state is MotionState.TIMEOUT:
        break                            # no reintentar: INCONCLUSIVE
    settled = settled + 1 if frame.motion.state is MotionState.QUIET_AFTER_MOTION and frame.ready.ready else 0
    if settled >= 4:                     # margen sobre min_readings para el consenso
        break

report = evaluate_spin(recorder.record(), ExternalBalance(before_ext, after_ext))
print(report.to_dict())
```

La página debe estar en primer plano, sin overlays ni scroll durante la secuencia. Playwright fija viewport/zoom/escala y recalcula la caja si hay desplazamiento. No sumar offsets del iframe dos veces.

## Reglas que aplica el código

- Spin por debajo del umbral ⇒ `None`; sin Spin no se registra clic. Un segundo clic lanza `SequenceError`.
- Reposo de rodillos ≠ liquidación: se exige además control listo visible y consenso de lecturas monetarias.
- OCR fallido ⇒ valor desconocido (nunca cero). El premio se lee de su propia región; nunca se deduce del balance.
- Consenso: ≥ 3 lecturas válidas en frames distintos separados en el tiempo; cualquier discrepancia ⇒ INCONCLUSIVE.
- Moneda ilegible ⇒ INCONCLUSIVE; moneda distinta observada ⇒ FAIL.
- Insuficiencia: frase específica en ≥ 3 frames, ningún giro pagado completado y balance estable durante la ventana completa.
- Movimiento reanudado tras el reposo ⇒ posible cascada/bonus ⇒ INCONCLUSIVE (requiere adaptación por juego).
- Sin balance externo de Playwright o con perfil no calibrado ⇒ nunca PASS de extremo a extremo.

## Qué falta para aprobar los escenarios reales

- Capturas y plantillas reales calibradas para cada juego/resolución y ambos mercados (com/EUR, pe/PEN).
- Clips etiquetados reales: victoria, derrota, bonus, rechazo, fallo OCR, resolución distinta, botón ausente y timeout.
- Adaptación específica para cascadas, bonus y premios animados.
- Integración con el balance externo y el informe global del equipo Playwright.

Las pruebas sintéticas verifican la lógica, no la compatibilidad con Betsson ni la precisión real del OCR. Esta entrega es una base implementada, no una certificación de los escenarios reales.
