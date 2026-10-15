# Malackathon 2026 — Intelligent Game Validation (betsson.es)

Automatiza la web real de Betsson, abre un juego de Pragmatic Play (Big Bass Bonanza) en Real Play y verifica lo que ve el jugador.

| Caso | Mercado | Idioma | Moneda | Escenario |
|---|---|---|---|---|
| T01 | betsson.es | Español | EUR | Giro completado |
| T02 | betsson.es | Español | EUR | Saldo insuficiente |

## Quién hace qué

- **Go (`runner/`)** controla el navegador con Playwright: login, saldo Betsson (DOM de la web exterior), abrir el juego, clics y capturas del rectángulo del juego. Decide PASS / FAIL / INCONCLUSIVE / ERROR y escribe el informe.
- **Python (`vision/vision_server.py`)** es un proceso que Go arranca una vez. Recibe rutas de capturas y devuelve JSON: importes leídos (o «desconocido»), movimiento entre capturas y mensajes. No toca el navegador ni decide resultados.
- **Configuración**: `config/es.json` es el mercado (URL, idioma, moneda, cuentas como nombres de variables de entorno, tiempos). Cada juego tiene su perfil en `config/games/<juego>/profile.json` con su calibración visual y sus plantillas (`spin.png`, `splash.png`).

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
go run ./runner -game bubble-up -case T02 # elegir juego (por defecto big-bass-bonanza)
```

## Juegos

| Juego | T02 real | T01 real | Notas |
|---|---|---|---|
| Big Bass Bonanza (`big-bass-bonanza`) | PASS | PASS | importes en amarillo; detección de giro por píxel |
| Bubble Up (`bubble-up`) | PASS | pendiente | importes en blanco; símbolos animados en reposo → detección por histograma de celdas (`motion_mode: cells`) |

Añadir un juego de Pragmatic Play:
1. Crear `config/games/<juego>/profile.json` con `game_name`, `game_path` (`/casino/tragaperras-slots/<juego>`) y `"calibrated": false`.
2. `go run ./runner -game <juego> -explore funded`: abre el juego y captura la pantalla de carga sin pulsar nada. Recortar `splash.png` (botón de entrada).
3. Repetir `-explore`: entra al juego y captura el marcador sin girar. Recortar `spin.png` y medir las regiones (`game_balance`, `bet`, `win`, `reels`, columnas exteriores) y el color del texto de los importes.
4. Marcar `"calibrated": true`, ejecutar T02 (gratis) y después T01 (un giro real). Un juego sin calibrar no puede ejecutar T01/T02.

El informe queda en `artifacts/<fecha>/report.md` (y `report.json`), con capturas por caso en `artifacts/<fecha>/T01/` y `T02/`.

## Dónde se ejecuta

Desde nuestros ordenadores. Los mentores indicaron que los servidores de EE. UU. (como los de GitHub Actions) tienen problemas con betsson.es, así que no hay workflow de CI.

## Estado

Ejecutado contra el juego real el 2026-10-15: T01 PASS (giro perdedor, 114,25 € − 2,00 € = 112,25 € en el juego y en Betsson) y T02 PASS (mensaje «Fondos insuficientes…», saldos sin cambios).

Limitaciones conocidas:
- Cada juego necesita su perfil calibrado (viewport 1280x720, capturas a 2x).
- El premio de un giro ganador se lee por OCR de la línea de premio y aún no se ha visto en una ejecución real: si no es legible, el caso sale INCONCLUSIVE.
- Un bonus (tiradas gratis) puede superar el tiempo límite: el caso sale INCONCLUSIVE, nunca se reintenta el giro.
- La cuenta financiada no debe usarse a la vez desde otro sitio: rompería la comprobación del saldo Betsson.
- Login y apertura del juego se reintentan una vez (antes de apostar); el giro nunca se reintenta.
- El navegador se lanza sin la marca de automatización (`--disable-blink-features=AutomationControlled`): sin ello el WAF de Betsson bloquea el login (403).
