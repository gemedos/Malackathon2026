1. Solución implementada para Pragmatic Play debe ser extensible a otros proveedores.

Flujo:

1. Entro en www.betson.com
2. Scroll hasta de sección proveedores.
3. Clic Pragmatic Play.
4. Entrar en juego.
5. Configurar sesión: cada vez que entres a una plataforma debes especificar cuánto tiempo vas a jugar y qué dinero quieres gastar.
6. Testear botones apuestas.
7. # Funciona? Acceso a saldo

# PROJECTS.md — Intelligent Game Validation

## 1. Project Overview

- **Project:** Malackathon 2026 — Intelligent Game Validation
- **Client:** Betsson Group
- **Objective:** Build an automated testing system that validates third-party casino games from the player's perspective.
- **Main challenge:** Interact with and validate casino games without accessing their internal DOM.
- **Target provider:** Pragmatic Play.
- **Target platform:** Betsson casino.
- **Expected result:** A working proof of concept that automatically executes casino game tests, validates their outcomes, and generates evidence-based reports.

### Core principle

- The system must verify what the player actually sees.
- Clicking a button does not constitute successful validation.
- The system must observe and verify the game's response.
- Tests must work even when game interfaces are rendered inside iframes or canvases.
- Computer vision, OCR, image recognition, and AI are permitted but not mandatory.
- The technology and architecture are freely selectable.

---

## 2. Functional Requirements

### FR-01 — Market Configuration

- [ ] Support two casino markets:
  - `betsson.com`
    - Language: English
    - Currency: EUR
  - `betsson.pe`
    - Language: Spanish
    - Currency: PEN
- [ ] Allow market configuration without modifying test logic.
- [ ] Validate the displayed currency against the selected market.
- [ ] Validate the expected language for relevant messages.
- [ ] Execute both testing scenarios independently for each market.

### FR-02 — Authentication

- [ ] Navigate to the correct Betsson casino lobby.
- [ ] Authenticate using the provided test accounts.
- [ ] Support funded accounts for successful-spin testing.
- [ ] Support accounts without sufficient funds for rejection testing.
- [ ] Never hard-code credentials.
- [ ] Never expose credentials in logs, screenshots, reports, recordings, or GitHub.

### FR-03 — Game Navigation

- [ ] Navigate through the casino lobby.
- [ ] Locate an available Pragmatic Play game.
- [ ] Launch the selected game.
- [ ] Enter **Real Play** mode.
- [ ] Confirm that the game has loaded successfully.
- [ ] Detect when the game is ready for interaction.
- [ ] Support games rendered inside iframes or canvases.
- [ ] Do not depend on access to the game's internal DOM.

### FR-04 — Visual Interaction

- [ ] Identify relevant game controls using visible information.
- [ ] Locate the Spin button.
- [ ] Read the displayed wager.
- [ ] Read the displayed currency.
- [ ] Read the displayed in-game balance.
- [ ] Read the Betsson account balance.
- [ ] Detect visible game state changes.
- [ ] Detect when a spin starts.
- [ ] Detect when a spin finishes.
- [ ] Read the visible spin outcome.
- [ ] Detect insufficient-balance messages.
- [ ] Verify results from visual evidence rather than assuming success after interaction.

---

## 3. Testing Scenarios

### SC-01 — Completed Real Play Spin

**Objective:** Verify that a real-money spin completes correctly and that balances reconcile.

#### Execution

- [ ] Open the casino lobby for the selected market.
- [ ] Authenticate with a funded test account.
- [ ] Launch an available Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read the Betsson balance before spinning.
- [ ] Read the in-game balance before spinning.
- [ ] Identify the displayed wager.
- [ ] Identify the displayed currency.
- [ ] Locate the Spin control.
- [ ] Trigger one spin.
- [ ] Verify visually that the spin started.
- [ ] Wait until the spin has completed.
- [ ] Verify visually that the spin finished.
- [ ] Read the settled outcome.
- [ ] Determine the payout from the observed outcome.
- [ ] Read the in-game balance after the spin.
- [ ] Read the Betsson balance after the spin.

#### Validation

- [ ] The spin started successfully.
- [ ] The spin completed successfully.
- [ ] The wager used matches the displayed wager.
- [ ] The displayed currency matches the selected market.
- [ ] The in-game balance is consistent with the completed spin.
- [ ] The Betsson balance reconciles with the wager and payout.

#### Balance Formula

```text
Expected balance after = Balance before - Wager + Payout
```

Validation:

```text
Actual balance after == Expected balance after
```

- A losing spin is valid.
- A winning spin is valid.
- The payout must be determined from the visible completed outcome.
- The test passes only when the observed balances are consistent with the completed spin.

---

### SC-02 — Insufficient Balance

**Objective:** Verify that a spin is rejected when the player has insufficient funds.

#### Execution

- [ ] Open the casino lobby for the selected market.
- [ ] Authenticate with the supplied insufficient-balance account.
- [ ] Launch an available Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read the Betsson balance before attempting the spin.
- [ ] Read the in-game balance before attempting the spin.
- [ ] Identify the displayed currency.
- [ ] Attempt a spin.
- [ ] Observe the game's response.
- [ ] Detect the insufficient-balance message.
- [ ] Read the Betsson balance after the attempt.
- [ ] Read the in-game balance after the attempt.

#### Validation

- [ ] The spin is rejected.
- [ ] No paid spin completes.
- [ ] An insufficient-balance message appears.
- [ ] The message is displayed in the expected language.
- [ ] The displayed currency matches the selected market.
- [ ] The Betsson balance remains unchanged.
- [ ] The in-game balance remains unchanged.

#### Expected Language

**English market:**

- Detect an appropriate insufficient-balance message in English.

**Peruvian market:**

- Detect an appropriate insufficient-balance message in Spanish.

The exact message text is not specified by the challenge and should not be assumed.

---

## 4. Test Matrix

The application must execute four test combinations.

| Test ID | Market      | Scenario             | Currency |
| ------- | ----------- | -------------------- | -------- |
| T01     | betsson.com | Completed Spin       | EUR      |
| T02     | betsson.com | Insufficient Balance | EUR      |
| T03     | betsson.pe  | Completed Spin       | PEN      |
| T04     | betsson.pe  | Insufficient Balance | PEN      |

### Requirements

- [ ] Execute all four combinations.
- [ ] Generate independent results for each combination.
- [ ] Identify every result by market and scenario.
- [ ] Include all required balance validations.
- [ ] Provide evidence supporting each test result.

---

## 5. Technical Requirements

The challenge does not prescribe a specific technology stack.

The following are **recommended implementation requirements**, not mandatory competition rules.

### TR-01 — Browser Automation

- [ ] Automate browser navigation.
- [ ] Support authentication.
- [ ] Support navigation through the casino lobby.
- [ ] Support launching third-party games.
- [ ] Capture screenshots during execution.
- [ ] Handle asynchronous game loading.

**Recommended technology:** Playwright.

### TR-02 — Computer Vision

- [ ] Capture screenshots of the game interface.
- [ ] Identify relevant visual elements.
- [ ] Locate interactive controls.
- [ ] Recognize game state changes.
- [ ] Detect visible messages.
- [ ] Extract displayed balances and wagers.

**Possible technologies:**

- OpenCV
- OCR
- Vision-language models
- Image recognition

Do not require all these technologies. Choose the simplest reliable approach.

### TR-03 — State Detection

- [ ] Identify when the game is loading.
- [ ] Identify when the game is ready.
- [ ] Identify when a spin starts.
- [ ] Identify when a spin completes.
- [ ] Identify when an error message appears.
- [ ] Avoid interpreting a successful click as a successful test.

### TR-04 — Balance Validation

- [ ] Extract monetary values from the visible interface.
- [ ] Identify the wager.
- [ ] Identify the payout.
- [ ] Calculate the expected final balance.
- [ ] Compare the expected balance against the observed balance.
- [ ] Validate both Betsson and in-game balances.
- [ ] Handle EUR and PEN.
- [ ] Use decimal-safe monetary calculations rather than floating-point equality.

### TR-05 — Reliability

- [ ] Wait for observable state changes instead of relying exclusively on fixed delays.
- [ ] Handle loading failures.
- [ ] Handle missing visual elements.
- [ ] Handle unexpected dialogs.
- [ ] Distinguish test failures from execution errors.
- [ ] Avoid reporting PASS when the result cannot be verified.

---

## 6. Reporting Requirements

### RR-01 — Test Results

- [ ] Generate a report after test execution.
- [ ] Identify the market.
- [ ] Identify the scenario.
- [ ] Display PASS/FAIL for every required validation.
- [ ] Include Betsson balance checks.
- [ ] Provide supporting visual evidence.

### RR-02 — Evidence

- [ ] Capture screenshots or equivalent visual evidence.
- [ ] Capture evidence of the initial game state.
- [ ] Capture evidence of the completed spin.
- [ ] Capture evidence of the resulting balances.
- [ ] Capture evidence of insufficient-balance rejection.
- [ ] Capture evidence of the unchanged balances.

### RR-03 — Recommended Report Format

```text
TEST REPORT

Market: betsson.com
Language: English
Currency: EUR

Scenario: Completed Real Play Spin

Game launched: PASS
Real Play activated: PASS
Initial balance detected: PASS
Wager detected: PASS
Spin started: PASS
Spin completed: PASS
Payout detected: PASS
Currency validated: PASS
In-game balance validated: PASS
Betsson balance validated: PASS

FINAL RESULT: PASS
```

This is an illustrative report format, not an actual test result.

---

## 7. GitHub Requirements

### GR-01 — Repository

- [ ] Store the source code in a GitHub repository.
- [ ] Organize the project clearly.
- [ ] Separate market configuration from test logic.
- [ ] Include the necessary dependencies.
- [ ] Include instructions for running the tests.
- [ ] Exclude credentials and secrets.

### GR-02 — GitHub Actions

- [ ] Create a GitHub Actions workflow.
- [ ] Execute the completed-spin scenario for both markets.
- [ ] Execute the insufficient-balance scenario for both markets.
- [ ] Run each scenario once per market.
- [ ] Generate the test report.
- [ ] Publish the report as a workflow artifact.
- [ ] Make supporting evidence accessible.

---

## 8. Security Requirements

- [ ] Use only the supplied test accounts.
- [ ] Obtain test credentials from Betsson.
- [ ] Coordinate with mentors to prepare insufficient-balance accounts.
- [ ] Never commit credentials.
- [ ] Never expose authentication secrets.
- [ ] Never include credentials in screenshots or recordings.
- [ ] Never include secrets in presentations or reports.
- [ ] Use the correct market configuration.

---

## 9. Deliverables

### D-01 — Source Code

- [ ] Working automated testing application.
- [ ] Public or accessible GitHub repository.
- [ ] Clear project structure.
- [ ] Market configuration.
- [ ] No committed credentials.

### D-02 — GitHub Actions

- [ ] Working CI workflow.
- [ ] Four test combinations executed.
- [ ] Published report.

### D-03 — Report and Evidence

- [ ] PASS/FAIL results for each check.
- [ ] Results identified by market and scenario.
- [ ] Betsson balance verification.
- [ ] Screenshots, trace, or video.

### D-04 — Presentation (Finalists Only)

- [ ] Prepare a seven-minute presentation.
- [ ] Demonstrate a working execution.
- [ ] Explain the architecture.
- [ ] Explain the technical decisions.
- [ ] Show how the system validates visible outcomes.

---

## 10. Evaluation Criteria

| Criterion                               |  Points |
| --------------------------------------- | ------: |
| Both scenarios work on both markets     |      30 |
| Validates the visible player experience |      20 |
| Code quality and architecture           |      15 |
| Reports and supporting evidence         |      15 |
| GitHub Actions integration              |      10 |
| Working demonstration                   |      10 |
| **Total**                               | **100** |
| Bonus                                   |     +10 |

**Maximum possible score: 110 points.**

The highest-priority requirements are successful execution of all four test combinations and reliable validation of visible game behavior.

---

## 11. Development Priorities

The following order is my recommendation for implementing the project during the hackathon.

### P0 — Essential

- [ ] Browser navigation.
- [ ] Authentication.
- [ ] Launch Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read balances and wager.
- [ ] Execute a spin.
- [ ] Verify spin completion visually.
- [ ] Validate balance reconciliation.
- [ ] Detect insufficient-balance rejection.
- [ ] Run both scenarios on both markets.

### P1 — Required Deliverables

- [ ] Automated PASS/FAIL reporting.
- [ ] Screenshots or equivalent evidence.
- [ ] GitHub Actions execution.
- [ ] Published reports.
- [ ] Secure credential handling.

### P2 — Improvements

- [ ] More robust computer vision.
- [ ] Improved error recovery.
- [ ] Better visual reporting.
- [ ] Additional supported games.
- [ ] Improved test reliability.

These improvements are optional and should not delay the mandatory functionality.

---

## 12. Definition of Done

The project is complete when:

- [ ] The application successfully authenticates on both markets.
- [ ] It launches an available Pragmatic Play game in Real Play.
- [ ] It validates a completed spin using visible evidence.
- [ ] It validates the Betsson and in-game balances.
- [ ] It correctly identifies insufficient-balance rejection.
- [ ] It verifies that balances remain unchanged after rejection.
- [ ] It produces results for all four market/scenario combinations.
- [ ] It generates a report with PASS/FAIL checks and supporting evidence.
- [ ] GitHub Actions executes the required tests and publishes the report.
- [ ] No credentials or secrets are exposed.

---

### Important architectural recommendation

**Don't start by building an autonomous AI agent.**

The challenge rewards reliable visual verification, not AI complexity.

For this hackathon, I would use:

**Playwright → Screenshots → Visual Recognition → State Validation → Reports → GitHub Actions**

This architecture directly addresses the challenge while keeping implementation manageable within the available development window.

The official brief gives **30 points for working scenarios and 20 for player-visible validation**. Together, these represent 50% of the base score. Prioritize those capabilities before adding advanced features.

---

## 13. Módulo de visión (`vision-module/`)

Módulo Python independiente (OpenCV + Tesseract) que recibe capturas del juego y devuelve PASS/FAIL/INCONCLUSIVE por validación. Uso y estructura: `vision-module/README.md`. Ejecución local sin Docker: `make setup`, `make test`, `make demo`.

### Límites

- Solo analiza imágenes: frames BGR del rectángulo visible del iframe, perfil del juego, timestamps y directorio de evidencias.
- No implementa navegador, login, lobby, credenciales, selección de juego, clics ni CI: eso es la parte Playwright, que le entrega las capturas.
- No consulta DOM del juego, canvas API, JavaScript, red, WebSocket ni estado privado. Sin agentes autónomos ni APIs de modelos.
- La configuración de mercados vive en `vision-module/config/markets.json`; la calibración de cada juego en `vision-module/config/profiles/`.

### Reglas de validación (no relajar)

- Spin con umbral configurable; si falta evidencia devuelve `None` y no se hace clic. Solo un intento de Spin por escenario; no reintentar tras timeout.
- Observar al menos un frame ANTES del clic. Reposo de rodillos ≠ liquidación: exigir además control listo visible y lecturas monetarias estables. Bonus/cascadas => INCONCLUSIVE hasta adaptarlos.
- OCR en una región por campo (saldo, apuesta, premio, moneda, mensaje); conservar texto, crop original y preprocesado. No inferir campos por el orden de números en una barra.
- Aceptar un valor solo con ≥ 3 lecturas iguales en frames distintos y separados en el tiempo; cualquier discrepancia => INCONCLUSIVE.
- Usar `Decimal`. Un OCR fallido nunca es cero. El premio se lee de su región; nunca se deduce del saldo final.
- Moneda observada explícitamente (EUR/€ en .com, PEN/S/ en .pe); ilegible => INCONCLUSIVE, distinta => FAIL.
- Rechazo por saldo insuficiente: frase específica en el idioma del mercado, ningún giro pagado completado y saldos sin cambios durante una ventana acotada. Una palabra genérica ("saldo", "balance") no prueba rechazo.
- Timestamps monotónicos, timeouts finitos, umbrales de movimiento y de reposo separados; nunca exigir diferencia exactamente cero.
- PASS solo con todas las evidencias; perfil sin calibrar o saldo Betsson ausente => nunca PASS.

### Honestidad sobre los datos

- Los perfiles de ejemplo y la demo (`make demo`) son sintéticos: no presentarlos como pruebas reales ni inventar plantillas.
- Pendiente: calibrar con capturas reales de cada juego y mercado, clips etiquetados (victoria, derrota, bonus, rechazo, fallo OCR, botón ausente, timeout) y adaptación de bonus/cascadas.
- No prometer fiabilidad ni compatibilidad universal sin datos reales. No guardar secretos; evidencias limitadas al rectángulo del juego.

# CLAUDE.md — Betsson Intelligent Game Validation (Malackathon 2026)

Este archivo contiene las reglas del proyecto. Son OBLIGATORIAS en cada sesión y en cada cambio.
Si una petición del usuario o una idea propia entra en conflicto con una regla marcada como
**NO NEGOCIABLE**, no la ejecutes: explica el conflicto y propón una alternativa que la cumpla.

---

## 1. Qué estamos construyendo

Una prueba de concepto que valida un juego de casino de terceros **como lo haría un jugador**, sin acceso
al DOM del juego (que se renderiza en un canvas dentro de un iframe):

1. Navega por la web de Betsson, inicia sesión y lanza un juego de Pragmatic Play en **Real Play**.
2. Valida dos escenarios usando lo que se ve en pantalla:
   - **Escenario 1**: spin completado en dinero real, con reconciliación de saldos.
   - **Escenario 2**: intento de spin con saldo insuficiente.
3. Se ejecuta en **GitHub Actions** y publica un informe pass/fail con evidencias.

Principio rector: **un click en Spin no es una prueba**. Hay que demostrar que el juego reaccionó, que el
spin terminó y que los saldos se comportaron como se espera.

---

## 2. Mercado (decisión del equipo)

**NO NEGOCIABLE: el único mercado es España, `https://www.betsson.es`.**

| Parámetro            | Valor                                      |
| -------------------- | ------------------------------------------ |
| Clave de mercado     | `es`                                       |
| URL base             | `https://www.betsson.es`                   |
| Ruta de proveedor    | `/casino/proveedores/{provider_slug}`      |
| Idioma esperado      | Español (`es`)                             |
| Locale del navegador | `es-ES`                                    |
| Zona horaria         | `Europe/Madrid`                            |
| Moneda esperada      | EUR (símbolo `€`)                          |
| Formato numérico     | decimal `,` y miles `.` (ej. `1.234,56 €`) |

- No uses betsson.com, betsson.pe ni otros dominios, aunque aparezcan en el PDF del reto o en código antiguo.
- Aun así, toda la configuración del mercado vive en `config/markets/es.yaml` y nunca en el código,
  para poder añadir mercados en el futuro sin refactorizar.
- Los mensajes que ve el jugador deben estar en **español** y los importes en **EUR**. Si no es así,
  el check correspondiente falla.

---

## 3. Seguridad y secretos

**NO NEGOCIABLE: no puede haber credenciales ni secretos en el repositorio, informes, capturas,
trazas, vídeos, logs ni en la presentación.**

- Las credenciales solo existen en variables de entorno:
  `BETSSON_ES_FUNDED_USER`, `BETSSON_ES_FUNDED_PASS`, `BETSSON_ES_EMPTY_USER`, `BETSSON_ES_EMPTY_PASS`.
  Lo mismo aplica a claves de API (por ejemplo `ANTHROPIC_API_KEY`).
- En local se cargan desde `.env` (en `.gitignore`). En CI vienen de GitHub Secrets.
- `.env.example` solo contiene los NOMBRES de las variables, con valores vacíos.
- Nunca escribas un valor real de credencial en ningún archivo, comentario, test, fixture, ejemplo,
  mensaje de commit ni respuesta. Si el usuario pega una credencial en el chat, no la copies a ningún archivo.
- Nunca imprimas, loguees ni incluyas credenciales en mensajes de error o de assert. Los errores dicen
  qué variable falta, nunca su valor.
- Las credenciales se representan con un objeto cuyo `__repr__`/`__str__` muestra `***`.
- En CI, enmascara también el usuario con `::add-mask::`.
- **Trazas**: Playwright guarda lo tecleado, así que la traza empieza DESPUÉS del login.
- **Vídeo**: se graba en un contexto nuevo creado tras el login (reutilizando `storage_state`), para
  que el formulario de login nunca aparezca.
- **Capturas** antes o durante el login: siempre con `mask=[...]` sobre los campos de usuario y contraseña.
- `storage_state` y cookies van en `.auth/` (en `.gitignore`), nunca se suben como artifact y se
  borran al final del job.
- Existe un test de higiene (`tests/test_secret_hygiene.py`) que busca los valores de las variables
  `BETSSON_*` en `artifacts/`. Debe ejecutarse siempre y no se puede desactivar ni debilitar.
- `.gitignore` incluye como mínimo: `.env`, `.auth/`, `artifacts/`, `test-results/`,
  `playwright-report/`, `__pycache__/`, `.venv/`.

### Límites de comportamiento

- **No** intentes saltar CAPTCHAs, verificación por email, 2FA ni sistemas anti-bot. Si aparecen,
  haz una captura enmascarada, falla con un mensaje claro y termina.
- **No** entres nunca en modo demo cuando se pide Real Play. Si solo hay botón de demo, el test falla.
- Usa solo las cuentas de prueba facilitadas por Betsson. La cuenta del escenario 2 la preparan
  los mentores; no intentes vaciar saldo con spins automáticos.
- Apuesta siempre la **mínima** y desactiva autoplay y turbo.

---

## 4. Validar lo que ve el jugador

**NO NEGOCIABLE: el pass/fail se basa en lo que es visible en pantalla, no en clicks codificados.**

- Fuera del juego (lobby, login, cabecera con el saldo de Betsson) se pueden usar selectores DOM.
  Aun así, el saldo de Betsson se lee también por OCR para respaldar la lectura "como jugador".
- Dentro del juego (canvas/iframe) se usa percepción visual: IA de visión, OCR por regiones y
  diferencia de píxeles entre fotogramas.
- La IA **aporta lecturas y localizaciones**, pero **nunca decide el pass/fail final**. Las reglas de
  verificación son código determinista en `src/validator/verify/`.
- Cada click dentro del juego se verifica: si la captura posterior no cambia, el click no cuenta.
- Si se usa la red (respuestas del servidor del juego), es solo un **oráculo de contraste**. Nunca
  sustituye la verificación visual.

---

## 5. Escenario 1 — Spin completado en Real Play

Pasos: abrir el lobby de betsson.es, autenticar con la cuenta con saldo, lanzar un juego de Pragmatic
Play en Real Play, leer el saldo de Betsson antes, identificar la apuesta y la moneda, localizar el
control y lanzar el spin, verificar que empezó y terminó, y leer el resultado y los saldos después.

Checks obligatorios, cada uno con su propio resultado en el informe:

| Check                            | Cómo se verifica                                                  |
| -------------------------------- | ----------------------------------------------------------------- |
| Spin iniciado                    | La zona de rodillos cambia por encima de un umbral tras el click  |
| Spin completado                  | Fotogramas estables durante N segundos y estado del juego "listo" |
| Apuesta mostrada = apuesta usada | OCR de la apuesta vs. bajada del saldo del juego al empezar       |
| Moneda = EUR                     | Símbolo `€` leído en apuesta y saldo                              |
| Saldo del juego coherente        | Cumple la regla de saldo                                          |
| Saldo Betsson reconcilia         | Cumple la regla de saldo (antes/después)                          |

**Regla de saldo:**

```
saldo_despues = saldo_antes - apuesta + premio
```

- `premio` es lo acreditado por el spin según lo que se ve en pantalla. Puede ser 0, porque perder
  también es un pass.
- Todo el dinero se maneja con `decimal.Decimal`, **nunca** con `float`.
- Tolerancia por defecto: 0. Cualquier tolerancia de redondeo tiene que ser explícita y estar documentada.
- Si el saldo de Betsson tarda en actualizarse, se sondea con timeout antes de declarar fallo.
- Si el spin activa bonos o giros gratis, se espera a que terminen o se marca como "no concluyente".
  Nunca se marca como pass sin pruebas.

---

## 6. Escenario 2 — Saldo insuficiente

Pasos: abrir el lobby, autenticar con la cuenta sin saldo utilizable, lanzar el juego en Real Play,
leer los saldos, intentar un spin, verificar la respuesta visible y leer los saldos después.

| Check                       | Cómo se verifica                           |
| --------------------------- | ------------------------------------------ |
| Spin rechazado              | Los rodillos no se mueven y no hay cargo   |
| Mensaje visible             | Se detecta un modal o aviso con texto      |
| Mensaje adecuado            | El texto indica saldo/fondos insuficientes |
| Idioma = español            | Detección de idioma sobre el texto leído   |
| Moneda = EUR                | Símbolo `€` visible                        |
| Saldo Betsson sin cambios   | Igual antes y después                      |
| Saldo del juego sin cambios | Igual antes y después                      |

El mensaje puede aparecer dentro del juego. Se valida lo que ve el jugador y se registra dónde apareció.

---

## 7. Arquitectura y convenciones

- Python 3.12, Playwright (Chromium), pytest, pydantic, PyYAML, python-dotenv, OCR y OpenCV/NumPy.
- Viewport fijo de 1280x720 y `device_scale_factor=1` (las coordenadas de visión dependen de ello).
- Proveedor y juego son **variables** (CLI `--provider` y `--game`, o las variables de entorno
  `PROVIDER` y `GAME`). Cambiarlos no debe requerir tocar código.
- La URL del proveedor se construye con `slugify(provider)` sobre la plantilla del mercado.
- Los selectores viven en `config/selectors/es.yaml`. No pongas selectores en el código y no inventes
  selectores CSS frágiles: usa `get_by_role`, `get_by_label` y `get_by_text`, con alternativas en español.
  Marca los no confirmados con `# TODO: verificar`.
- Las coordenadas y regiones de lectura de cada juego se cachean en `config/games/<juego>.yaml`, en
  formato normalizado (0–1) respecto al iframe.
- Usa page objects para la web de Betsson, un driver para el juego, verificadores puros y un módulo de evidencias.
- Usa el módulo `logging`, sin datos sensibles. Código tipado y con docstrings breves.

---

## 8. Evidencias e informe

- Cada check se identifica por **escenario + mercado + nombre** y tiene esperado, observado,
  resultado (pass/fail/no concluyente) y evidencia.
- Las evidencias son capturas anotadas (cajas y valores leídos), una tira de fotogramas del spin, el
  vídeo posterior al login y la traza posterior al login.
- `artifacts/results.json` es la fuente única; de él se generan el HTML y el resumen del job.
- Antes de dar por buena cualquier evidencia, confirma que no contiene datos de login.

---

## 9. GitHub Actions

- El workflow ejecuta **ambos escenarios** en el mercado `es` y publica el informe.
- Incluye `workflow_dispatch` (inputs `provider` y `game`) y una ejecución programada con `schedule`.
- Los secretos llegan solo por `${{ secrets.* }}` en `env:`.
- `upload-artifact` sube `artifacts/` excluyendo `.auth/`. Hay un paso `rm -rf .auth` con `if: always()`.
- El test de higiene de secretos se ejecuta con `if: always()`.
- El resumen pass/fail se escribe en `$GITHUB_STEP_SUMMARY`.

---

## 10. Checklist antes de cada commit

- [ ] Ningún archivo contiene credenciales, tokens ni claves (revísalo con `git diff --cached`).
- [ ] `.env`, `.auth/` y `artifacts/` no están en el commit.
- [ ] Solo se usa `https://www.betsson.es`.
- [ ] Ningún check se marca como pass solo por haber hecho click.
- [ ] El dinero se maneja con `Decimal`.
- [ ] Los selectores y la configuración están en YAML, no en el código.
- [ ] Los tests de higiene de secretos pasan.

Si no puedes cumplir alguna de estas reglas, detente y avisa al usuario en lugar de seguir.
