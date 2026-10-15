# Malackathon 2026 — Intelligent Game Validation (betsson.es)

Automatiza la web real de Betsson, abre un juego de Pragmatic Play (Big Bass Bonanza) en Real Play y verifica lo que ve el jugador.

| Caso | Mercado | Idioma | Moneda | Escenario |
|---|---|---|---|---|
| T01 | betsson.es | Español | EUR | Giro completado |
| T02 | betsson.es | Español | EUR | Saldo insuficiente |

## Quién hace qué

- **Go (`runner/`)** controla el navegador con Playwright: login, saldo Betsson (DOM de la web exterior), abrir el juego, clics y capturas del rectángulo del juego. Decide PASS / FAIL / INCONCLUSIVE / ERROR y escribe el informe.
- **Python (`vision/vision_server.py`)** es un proceso que Go arranca una vez. Recibe rutas de capturas y devuelve JSON: importes leídos (o «desconocido»), movimiento entre capturas y mensajes. No toca el navegador ni decide resultados.
- **Configuración (`config/es.json`)**: mercado, juego, cuentas (solo nombres de variables de entorno), regiones de lectura y tiempos.

Reglas: un importe ilegible nunca es cero; sin evidencia completa no hay PASS; no se lee el DOM interno del juego.

## Instalación (macOS o Linux)

Requisitos: Go 1.24+, Python 3.12, Node 18+, Tesseract con español (`brew install tesseract tesseract-lang` o `apt install tesseract-ocr tesseract-ocr-spa`).

```bash
python3 -m venv vision/.venv && vision/.venv/bin/pip install -r vision/requirements.txt
scripts/install_playwright.sh
cp .env.example .env   # rellenar con las cuentas que proporciona Betsson
```

## Ejecución

```bash
go test ./runner                         # prueba sintética Go↔Python (sin Betsson)
go run ./runner -explore funded -headed  # calibración: login, abrir juego y capturas, SIN apostar
go run ./runner -case T01                # giro real con la apuesta visible en el juego (hoy 2,00 €)
go run ./runner -case T02                # intento con la cuenta sin saldo
go run ./runner                          # ambos
go run ./runner -serve localhost:8080    # interfaz local (Go + htmx + Tailwind) para lanzar casos y ver evidencias
```

El informe queda en `artifacts/<fecha>/report.md` (y `report.json`), con capturas por caso en `artifacts/<fecha>/T01/` y `T02/`.

## Dónde se ejecuta

Desde nuestros ordenadores. Los mentores indicaron que los servidores de EE. UU. (como los de GitHub Actions) tienen problemas con betsson.es, así que no hay workflow de CI.

## Estado

Ejecutado contra el juego real el 2026-10-15: T01 PASS (giro perdedor, 114,25 € − 2,00 € = 112,25 € en el juego y en Betsson) y T02 PASS (mensaje «Fondos insuficientes…», saldos sin cambios).

Limitaciones conocidas:
- Calibrado para Big Bass Bonanza con viewport 1280x720 y capturas a 2x (`config/es.json`, `config/templates/`).
- El premio de un giro ganador se lee por OCR de la línea de premio y aún no se ha visto en una ejecución real: si no es legible, el caso sale INCONCLUSIVE.
- Un bonus (tiradas gratis) puede superar el tiempo límite: el caso sale INCONCLUSIVE, nunca se reintenta el giro.
- La cuenta financiada no debe usarse a la vez desde otro sitio: rompería la comprobación del saldo Betsson.
- El navegador se lanza sin la marca de automatización (`--disable-blink-features=AutomationControlled`): sin ello el WAF de Betsson bloquea el login (403).
