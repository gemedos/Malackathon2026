# Mapa del proyecto (para depurar sin ayuda)

Lanzas un test y todo ocurre en este orden. Cada paso escribe una línea en `artifacts/es/run.log`:
busca el último mensaje `INFO`/`WARNING` y mira la tabla.

| Paso | Qué hace | Archivo | Si falla, toca… |
|---|---|---|---|
| 1 | Login y cookies | `src/validator/navigation.py`, `pages/login_page.py` | `config/selectors/es.yaml` → `login:`, `cookies:` |
| 2 | Página del proveedor y tarjeta del juego | `pages/provider_page.py` | `es.yaml` → `provider:`, `game_card:` |
| 3 | Real Play | `pages/game_page.py` (`wait_loaded`) | `es.yaml` → `game_launch.real_play` |
| 4 | Avisos y pantallas previas (aviso de sesión, límites, torneos) | `pages/game_page.py` (`handle_pregame`) | `es.yaml` → `game_launch.pregame` (el orden importa: arriba = prioridad) |
| 5 | Pantalla de carga del juego (pulsar Spin) y HUD | `src/validator/game/scenarios.py` (`_reach_hud`) | `config/games/<proveedor>/_default.yaml` (+ `splash.png`) |
| 6 | Leer saldo, apuesta y premio (OCR) | `vision-module/vision_engine/ocr.py` | regiones en `_default.yaml` |
| 7 | Un Spin y veredicto | `scenarios.py` + `vision_engine/evaluation.py` | `settle`, `idle_patterns` en `_default.yaml` |
| 8 | Saldo de Betsson antes y después | `src/validator/game/account.py` | `es.yaml` → `account.balance` |

Ver el juego mientras falla: `artifacts/es/<proveedor>/<juego>/<escenario>/` tiene `video.webm` (lo más útil),
capturas y `vision/` (recortes que ha leído el OCR). `trace.zip` es ligera (acciones y errores); se abre con
`playwright show-trace trace.zip`.

Una pantalla nueva que tapa el juego se arregla SOLO en `es.yaml` → `pregame` (nombre, cómo detectarla, qué pulsar).
Un paso puede ser una lista de alternativas: se pulsa la primera visible.
