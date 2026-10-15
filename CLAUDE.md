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

| Parámetro | Valor |
| --- | --- |
| Clave de mercado | `es` |
| URL base | `https://www.betsson.es` |
| Ruta de proveedor | `/casino/proveedores/{provider_slug}` |
| Idioma esperado | Español (`es`) |
| Locale del navegador | `es-ES` |
| Zona horaria | `Europe/Madrid` |
| Moneda esperada | EUR (símbolo `€`) |
| Formato numérico | decimal `,` y miles `.` (ej. `1.234,56 €`) |

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

| Check | Cómo se verifica |
| --- | --- |
| Spin iniciado | La zona de rodillos cambia por encima de un umbral tras el click |
| Spin completado | Fotogramas estables durante N segundos y estado del juego "listo" |
| Apuesta mostrada = apuesta usada | OCR de la apuesta vs. bajada del saldo del juego al empezar |
| Moneda = EUR | Símbolo `€` leído en apuesta y saldo |
| Saldo del juego coherente | Cumple la regla de saldo |
| Saldo Betsson reconcilia | Cumple la regla de saldo (antes/después) |

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

| Check | Cómo se verifica |
| --- | --- |
| Spin rechazado | Los rodillos no se mueven y no hay cargo |
| Mensaje visible | Se detecta un modal o aviso con texto |
| Mensaje adecuado | El texto indica saldo/fondos insuficientes |
| Idioma = español | Detección de idioma sobre el texto leído |
| Moneda = EUR | Símbolo `€` visible |
| Saldo Betsson sin cambios | Igual antes y después |
| Saldo del juego sin cambios | Igual antes y después |

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
