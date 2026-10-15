"""Puente entre Playwright (navegador) y vision_engine (lectura visual del juego).

- calibration: config/games/<proveedor>/<juego>.yaml (regiones normalizadas 0–1) -> perfil de visión.
- driver:      capturas del iframe y clics por coordenadas (nunca DOM del juego).
- account:     saldo Betsson de la cabecera (DOM permitido fuera del juego, respaldado por OCR).
- scenarios:   ejecuta Escenario 1 / Escenario 2 y devuelve el informe por check.
"""
