# Alcance: motor de visión del juego

Este archivo sustituye las instrucciones de trabajo para el equipo OpenCV + OCR. Se ha redactado desde el texto aportado; no se dispone del CLAUDE.md original.

## Objetivo

Implementar y calibrar exclusivamente un módulo Python independiente que observe el rectángulo visible del juego mediante imágenes y permita verificar los dos escenarios en betsson.com (en/EUR) y betsson.pe (es/PEN).

## Límites del módulo

- Recibir frames BGR, perfil del juego, timestamps y directorio de evidencias.
- Devolver coordenadas locales, confianza, textos OCR, importes, estados visuales y errores explícitos.
- No implementar login, lobby, credenciales, selección de juego, navegador ni CI del proyecto principal. Son responsabilidad del equipo Playwright.
- No consultar DOM interno, canvas API, JavaScript del juego, red, WebSocket ni estado privado.
- No incorporar agentes autónomos ni APIs de modelos en esta entrega.
- El equipo externo captura el rectángulo del iframe visible y ejecuta los clics. No es necesario localizar un canvas dentro del iframe.

## Prioridades y aceptación

- [ ] P0: calibrar un juego real, resolución, plantilla Spin y regiones independientes: balance, apuesta, premio, moneda, rodillos y mensaje.
- [ ] P0: localizar Spin con umbral configurable y devolver None cuando falte evidencia.
- [ ] P0: convertir coordenadas de imagen a coordenadas CSS teniendo en cuenta offset y escala.
- [ ] P0: observar un frame ANTES del único clic y después secuencia temporal; demostrar movimiento y posterior reposo.
- [ ] P0: no confundir reposo de rodillos con liquidación. Exigir además control listo visible y lecturas monetarias estables; bonus/cascadas necesitan adaptación específica.
- [ ] P0: OCR en regiones por campo; conservar texto y crop original/preprocesado. No inferir campos por orden de números en una barra completa.
- [ ] P0: repetir lecturas en al menos tres frames distintos, con separación temporal, antes de aceptar balance/apuesta/premio/moneda.
- [ ] P0: usar Decimal; nunca convertir fallo de OCR en cero ni deducir premio a partir del balance final.
- [ ] P0: validar balance_final = balance_inicial - apuesta + premio observado independientemente.
- [ ] P0: insuficiencia requiere mensaje específico en idioma esperado, ausencia de giro pagado completado y balance sin cambios durante ventana acotada. Una palabra genérica no prueba rechazo.
- [ ] P0: moneda debe observarse explícitamente; EUR o símbolo € para com; PEN o S/ para pe. Moneda ilegible => inconcluso.
- [ ] P1: devolver PASS/FAIL/INCONCLUSIVE por aserción con referencias a evidencias. Balance externo lo aporta y valida Playwright; no declarar validación integral sin él.
- [ ] P1: probar clips etiquetados y capturas reales de ambos mercados; incluir fallo OCR, resolución diferente, botón ausente, timeout, victoria, derrota, bonus y rechazo.

## Reglas de implementación

- Usar Docker como entorno de ejecución: `docker compose build` y `docker compose run --rm vision`. Para capturas, ejecutar `offline.py` dentro de ese servicio; consultar README.md. Mantener el módulo sin navegador.

- El perfil de ejemplo es ilustrativo y no está calibrado. No inventar plantillas ni presentar fixtures sintéticos como pruebas reales.
- Timestamps monotónicos, timeouts finitos y umbrales de movimiento separados de reposo. Nunca exigir diferencia exactamente cero.
- Solo un intento de Spin por escenario. No reintentar tras timeout incierto.
- Mantener dependencias OpenCV, NumPy y Tesseract locales. Tesseract y sus idiomas son dependencias del sistema.
- No prometer fiabilidad, puntuación o compatibilidad universal sin datos reales.
- No guardar secretos; evidencias limitadas al rectángulo del juego.

## Estado de esta entrega

Incluye matching de Spin, OCR por campo con evidencias, parser monetario y de moneda, transformación de coordenadas, seguimiento temporal, detector de control listo por plantillas, consenso temporal de OCR, registro de un único intento y evaluación PASS/FAIL/INCONCLUSIVE por aserción, runner offline y pruebas sintéticas. NO incluye perfiles ni plantillas calibrados, adaptación de bonus/cascadas ni validación real contra Betsson. Esos puntos deben completarse antes de declarar PASS de extremo a extremo.
