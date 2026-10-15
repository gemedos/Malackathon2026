# CLAUDE.md — Malackathon 2026: Intelligent Game Validation

## Lectura inicial y fuente

Lee AGENTS.md en la raíz y aplica sus preferencias de tecnología, simplicidad, nombres y comunicación. No asumas que Claude lee AGENTS.md automáticamente: este archivo lo exige expresamente.

Fuente de requisitos: PDF «Malackathon 2026 — Intelligent Game Validation — Student challenge», Betsson Group, 15–16 de octubre de 2026, tres páginas. El PDF define el reto; las tecnologías de AGENTS.md son elecciones del usuario, no condiciones de la competición. Si un detalle no aparece en el PDF, tratarlo como propuesta o dato por confirmar.

Queremos reconstruir un prototipo pequeño y comprensible. No reutilizar automáticamente toda la arquitectura previa ni borrar trabajo existente. Primero revisar y proponer qué conservar y cómo aislar el nuevo trabajo.

## Objetivo

Automatizar la experiencia existente de Betsson, abrir un juego de Pragmatic Play en Real Play y verificar lo que ve el jugador. No estamos construyendo una web de casino.

El juego puede estar en un iframe o canvas. No depender del DOM interno ni del estado privado del juego para validar sus controles, mensajes o resultados. Playwright puede manejar la web exterior y capturar el rectángulo visible del juego; la visión en Python interpreta sus píxeles. Un clic no demuestra que el juego haya reaccionado correctamente.

El PDF permite elegir cualquier juego de Pragmatic Play disponible en el mercado. No exige Sweet Bonanza ni que un mismo título exista en ambos mercados. Visión, OCR y AI son opciones del PDF; aquí se elige visión en Python por preferencia del usuario.

## Matriz obligatoria

| Caso | Mercado    | Idioma esperado | Moneda | Escenario          |
| ---- | ---------- | --------------- | ------ | ------------------ |
| T01  | betsson.es | Español         | EUR    | Giro completado    |
| T02  | betsson.es | Español         | EUR    | Saldo insuficiente |

- [ ] Configurar mercado, idioma, moneda, juego y cuenta sin duplicar la lógica del escenario.
- [ ] Ejecutar los dos escenarios en betsson.es (alcance acordado: un solo mercado).
- [ ] Identificar cada resultado y evidencia por mercado y escenario.

## Escenario 1: giro completado en Real Play

### Recorrido

- [ ] Abrir el lobby del mercado.
- [ ] Iniciar sesión con la cuenta de pruebas financiada que proporcione Betsson. Credenciales en .env
- [ ] Abrir un juego disponible de Pragmatic Play en Real Play.
- [ ] Leer el saldo de Betsson antes del giro e identificar apuesta y moneda visibles.
- [ ] Localizar visualmente el control y lanzar un giro.
- [ ] Observar que el juego reaccionó, el giro comenzó y terminó.
- [ ] Leer el resultado liquidado, el premio observado y los saldos posteriores.

### Aserciones

- [ ] El giro empezó y terminó; no basta con enviar un clic.
- [ ] La apuesta mostrada es la aplicada al giro; aportar evidencia y no darlo por supuesto.
- [ ] La moneda mostrada corresponde al mercado.
- [ ] El saldo del juego es consistente con el giro completado.
- [ ] El saldo Betsson anterior y posterior satisface:

```text
saldo_despues = saldo_antes - apuesta + premio
```

Premio significa el importe acreditado por el giro terminado según el resultado observado en pantalla. Un giro perdedor también puede aprobar. No deducir el premio del saldo final para luego verificar ese mismo saldo: sería una comprobación circular.

## Escenario 2: saldo insuficiente

- [ ] Coordinar con mentores una cuenta suministrada sin saldo utilizable para la apuesta intentada.
- [ ] Abrir lobby, autenticar y abrir un juego disponible de Pragmatic Play en Real Play.
- [ ] Leer los saldos antes del intento.
- [ ] Intentar un giro y observar la respuesta visible.
- [ ] Leer los saldos después del intento.
- [ ] Verificar que el intento se rechaza y no termina como giro pagado.
- [ ] Verificar un mensaje adecuado de saldo insuficiente en el idioma del mercado, incluso si está dentro del juego.
- [ ] Verificar moneda correcta.
- [ ] Verificar que NO cambian ni el saldo Betsson ni el saldo del juego.

El PDF no prescribe una frase exacta. No considerar palabras sueltas como «saldo» o «balance» prueba suficiente de rechazo. No preparar el saldo agotando fondos con giros repetidos por iniciativa propia: coordinarlo con mentores.

## Architecture proposal — confirm before implementation

Prefer this minimal architecture:

- Go uses Playwright through playwright-go to open Betsson, log in, find and launch games, capture screenshots and execute interactions.
- Go coordinates the tests, validates balance calculations and produces the final report.
- A separate Python module uses OpenCV and OCR to interpret game screenshots. It returns detected controls, coordinates, monetary readings, messages and visual states. It does not control the browser or decide the overall test result.
- Go saves screenshots and passes their paths to Python. Python returns structured JSON observations, including uncertainty or reading errors.
- Go starts Python as a subprocess. Initially, prefer one persistent Python process per test run so temporal observations can be tracked without repeatedly loading dependencies.
- Do not introduce an HTTP server, database, queues or web interface unless we explicitly agree they are needed.
- Market scope: betsson.es only, Spanish and EUR.
- Do not inspect the game’s internal DOM or private state. Use the outer website DOM for navigation and screenshots for game validation.
- Missing or ambiguous evidence must never produce a PASS.

Before implementing, explain one complete test journey in plain language: which component acts, what it receives, what it returns and how the final result is determined.

Ask me to approve this architecture first. Explain any proposed structural change before making it. Keep explanations concise and assume I will not read the source code.

## Criterios internos para evitar falsos positivos

Estas son reglas de implementación del prototipo, no requisitos adicionales del PDF:

- Usar aritmética monetaria exacta: unidades menores enteras o Decimal en Python; evitar float para comparar dinero.
- Un valor ilegible es desconocido, nunca cero. Un premio cero debe observarse o justificarse por una señal visual calibrada del juego.
- Calibrar resolución, regiones y plantillas sobre capturas reales; los ejemplos no son evidencia real.
- Transformar coordenadas de captura a coordenadas del navegador considerando escala y posición del juego.
- Observar antes y después de la acción. Limitar tiempos de espera y controlar huecos entre capturas.
- Reposo de rodillos por sí solo no prueba liquidación. Combinarlo con señales visuales de disponibilidad y lecturas estables; contemplar bonus y cascadas del juego elegido.
- Repetir lecturas cuando sea necesario para confirmar importes. No convertir una coincidencia débil de OCR en un PASS.
- No reintentar automáticamente un giro de resultado incierto: podría producir una apuesta adicional.
- Separar fallo demostrado, evidencia insuficiente y error de ejecución. No aprobar comprobaciones no verificadas.
- El informe debe mostrar PASS/FAIL por comprobación como pide el PDF. Si falta evidencia, registrar explícitamente INCONCLUSIVE/ERROR, impedir un PASS global y explicar por qué; no presentar ese caso como aprobado.
- No declarar el escenario completo aprobado sin verificar el saldo Betsson, aunque la parte visual funcione.

## Entregables obligatorios

- [ ] Código organizado en GitHub, configuración por mercado y sin secretos.
- [ ] Instrucciones reproducibles de instalación y ejecución.
- [x] ~~GitHub Actions~~: descartado por indicación de los mentores (problemas con servidores de EE. UU.). Se ejecuta desde nuestros ordenadores.
- [ ] Informe por comprobación, escenario y mercado, incluyendo saldos Betsson.
- [ ] Capturas, traza o vídeo que respalden los resultados.
- [ ] Solo si somos finalistas: presentación de siete minutos el 16 de octubre, con ejecución funcional y explicación de decisiones técnicas.

El PDF pone page objects, fixtures y utilidades como ejemplos; no obliga a esas capas. No crear abstracciones por cumplir un supuesto requisito.

## Cuentas, credenciales y evidencias

- Usar las cuentas de pruebas suministradas por Betsson; nunca inventar cuentas o credenciales.
- No incluir secretos en código, repositorio, informes, capturas, grabaciones ni presentación.
- Usar variables de entorno/secrets del entorno de ejecución, sin imprimirlos.
- Evitar capturar pantallas de autenticación o datos sensibles; revisar artefactos antes de publicarlos.
- Si faltan cuentas, acceso o estado de saldo adecuado, informar del bloqueo y continuar únicamente con tareas independientes. No simular una ejecución real como si hubiera ocurrido.

## Prioridad durante el hackathon

1. Acordar el diseño mínimo y la integración Go/Python/Playwright.
2. Conseguir un recorrido vertical real en un mercado y un juego: abrir, observar, interactuar y validar.
3. Completar saldo insuficiente y los dos casos de la matriz.
4. Dejar evidencias e informe claros (ejecución local; GitHub Actions descartado por los mentores).
5. Mejorar robustez y preparar la demo. No añadir extras antes de completar lo obligatorio.

Las evidencias deben acompañar al desarrollo desde el primer recorrido; no posponerlas hasta el final.

## Evaluación del PDF

| Criterio                                               | Peso |
| ------------------------------------------------------ | ---: |
| Escenarios en ambos mercados, incluidos saldos Betsson |   30 |
| Verificación de la experiencia visible                 |   20 |
| Código y arquitectura                                  |   15 |
| Informe y evidencias                                   |   15 |
| GitHub Actions                                         |   10 |
| Demo                                                   |   10 |

Cada criterio se puntúa de 1 a 5; puntos = puntuación / 5 × peso. Máximo base: 100. Bonus: hasta 10 por trabajo adicional, con motivo escrito; máximo total: 110. Ninguna tecnología garantiza puntos por sí sola.

## Definición de terminado

Los dos casos (T01 y T02) se han ejecutado realmente con las cuentas suministradas, todas las comprobaciones obligatorias están respaldadas por evidencia, los saldos se verifican, el informe se genera localmente con sus evidencias y no hay secretos expuestos. Si hay casos inconclusos o bloqueados, declararlos pendientes, sin presentar el proyecto como terminado.

## Primera respuesta esperada de Claude

Explicar brevemente qué se construirá y qué hace cada componente. Revisar el repositorio y detectar trabajo sin guardar o instrucciones antiguas. Proponer el camino más simple y consultar las decisiones estructurales pendientes según AGENTS.md antes de implementarlas. No comenzar con una reescritura masiva ni una lista extensa de preguntas.
