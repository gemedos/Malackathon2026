# Malackathon 2026 — Betsson Intelligent Game Validation

Prueba de concepto que valida un juego de casino **como lo haría un jugador** en
[betsson.es](https://www.betsson.es). Este módulo cubre la **navegación**: desde abrir betsson.es hasta
tener el juego cargado en **Real Play** (dinero real). La capa de visión dentro del canvas se construirá
sobre la `GameSession` que devuelve este módulo.

> Las reglas del proyecto están en [CLAUDE.md](CLAUDE.md) y son obligatorias.

## Instalación

Requiere Python 3.12 (CI) — también funciona con 3.11 en local.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # en Linux/CI: --with-deps chromium
```

## Credenciales en local (`.env`)

```bash
cp .env.example .env
```

Rellena **solo en tu máquina** las variables de `.env` (está en `.gitignore`):

| Variable                                            | Uso                                                 |
| --------------------------------------------------- | --------------------------------------------------- |
| `BETSSON_ES_FUNDED_USER` / `BETSSON_ES_FUNDED_PASS` | Cuenta de prueba con saldo (escenario 1)            |
| `BETSSON_ES_EMPTY_USER` / `BETSSON_ES_EMPTY_PASS`   | Cuenta de prueba sin saldo utilizable (escenario 2) |

`.env` se carga solo si existe. Si falta una variable, el error dice **cuál** falta, nunca su valor.

## Credenciales en CI (GitHub Secrets)

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**, y crea los cuatro
secretos anteriores. O con la CLI de GitHub (pide el valor de forma interactiva, sin dejarlo en el historial):

```bash
gh secret set BETSSON_ES_FUNDED_USER
gh secret set BETSSON_ES_FUNDED_PASS
gh secret set BETSSON_ES_EMPTY_USER
gh secret set BETSSON_ES_EMPTY_PASS
```

Opcionalmente, en **Variables** puedes definir `DEFAULT_GAME` (formato `Proveedor / Juego`) para la
ejecución programada. Para el workflow de catálogo hace falta además `CATALOG_PAT` (ver más abajo).

## Ejecutar en local

```bash
pytest tests --provider "Pragmatic Play" --game "Sweet Bonanza"
pytest tests --game "Pragmatic Play / Sweet Bonanza"            # formato del desplegable
pytest tests --provider "PlaynGo"                               # todos los juegos del proveedor
pytest tests --provider "Pragmatic Play" --game "Gates of Olympus" --headed
pytest tests/test_secret_hygiene.py                             # ejecútalo siempre después
```

| Opción CLI   | Variable de entorno | Por defecto                                              |
| ------------ | ------------------- | -------------------------------------------------------- |
| `--provider` | `PROVIDER`          | — (obligatorio salvo que el juego lo incluya)            |
| `--game`     | `GAME`              | vacío = todos los juegos del proveedor                   |
| —            | `GAMES_JSON`        | lista JSON de juegos (la usa el workflow para cada lote) |
| `--account`  | `ACCOUNT`           | `FUNDED`                                                 |
| `--market`   | `MARKET`            | `es`                                                     |
| `--headed`   | `HEADED=1`          | headless                                                 |

El CLI tiene prioridad sobre el entorno. Cambiar de proveedor o de juego **no requiere tocar código**.
Cada juego es un caso de test (`test_navigation[sweet-bonanza]`). El login se hace **una vez** por
ejecución y todos los juegos comparten el contexto de trabajo.

El nombre del juego debe coincidir exactamente (sin distinguir mayúsculas ni tildes). Si no, el test
falla y lista las candidatas que encontró (`Sweet Bonanza 1000`, `Sweet Bonanza Xmas`...).

### Qué hace cada juego

1. Abre `https://www.betsson.es/casino/proveedores/<slug>` (`slugify("Pragmatic Play") = pragmatic-play`).
   Si da 404 o redirige, usa el **plan B** (lobby y buscador) y lo registra.
2. Busca la tarjeta (alt / aria-label / texto, con el buscador o con scroll) y la lanza con un botón
   de `real_play_labels`. Si solo hay demo, **falla**.
3. Espera el iframe (tamaño mínimo y estable 2 s) y el canvas (capturas cada 500 ms hasta que dos
   seguidas casi no difieran; timeout de 60 s).

### Datos que genera (todavía no hay informe)

En `artifacts/es/`:

- `navigation_results.json`: un registro por check (escenario, mercado, proveedor, juego, check, estado,
  detalle, evidencia). Es la fuente de la que saldrá el informe cuando terminen los escenarios.
- `run.log`.
- `<proveedor>/<juego>/`: `provider_page.png`, `game_card.png`, `game_loaded.png`, `video.webm` y
  `trace.zip`. La traza se abre con `python -m playwright show-trace <ruta>/trace.zip`.

## Catálogo de proveedores y juegos

`config/catalog/es.json` contiene los proveedores con página en betsson.es y sus tragaperras
(`catalog.game_types` en `config/markets/es.yaml`). Se obtiene abriendo `/casino/proveedores` en un
navegador normal y capturando las APIs públicas que carga la propia web (`/api/v2/games` y
`/api/v1/game-studios`). Después se cruza con los enlaces `/casino/proveedores/<slug>` de la página.

```bash
python scripts/update_catalog.py                # scrape + catálogo + desplegables de tests.yml
python scripts/update_catalog.py --render-only  # solo regenera los desplegables desde el catálogo
```

Si el scrape trae menos de `min_providers` / `min_games`, no se sobrescribe nada.

## Configuración

| Archivo                    | Contenido                                                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `config/markets/es.yaml`   | URL base, plantilla de proveedor, locale, zona horaria, moneda, textos de Real Play/demo, tiempos                  |
| `config/selectors/es.yaml` | Selectores como **listas de alternativas** (`get_by_role`, `get_by_label`, `get_by_placeholder`, `get_by_text`...) |

El código no contiene valores de mercado ni selectores. `find_first()` registra en el log qué alternativa
funcionó: úsalo para confirmar selectores y quitar el `# TODO: verificar con inspect_site.sh`.

## Inspeccionar el sitio (`scripts/inspect_site.sh`)

Abre `playwright codegen` con el viewport, idioma y zona horaria de los tests:

```bash
./scripts/inspect_site.sh                    # portada de betsson.es
./scripts/inspect_site.sh "Pragmatic Play"   # página del proveedor
```

Usa el inspector para leer el rol y el nombre accesible de cada elemento y añádelo como alternativa en
`config/selectors/es.yaml`. **No grabes el login**: codegen muestra lo que tecleas; nunca guardes ni
compartas un script o captura con credenciales.

## GitHub Actions

### `Tests betsson.es` (`.github/workflows/tests.yml`)

**Actions → Tests betsson.es → Run workflow**:

- **Proveedor**: desplegable con los 44 proveedores del catálogo.
- **Juego**: desplegable `Proveedor / Juego` con las ~2.100 tragaperras. La opción
  `(todos los juegos del proveedor)` prueba todos los juegos del proveedor elegido.

GitHub no permite desplegables dinámicos ni dependientes entre sí. Si eliges un juego, **manda su
proveedor**: si no coincide con el del primer desplegable, se avisa y se usa el del juego.

Jobs:

1. `plan`: valida la selección contra el catálogo y reparte los juegos en lotes de 20.
2. `Lote N` (matriz con `max-parallel: 1`): los lotes van de uno en uno, porque todos usan la misma
   cuenta de dinero real. Cada lote hace login una vez y ejecuta `pytest tests` (todos los tests salvo el
   de higiene) sobre sus juegos. Después pasa el test de higiene (`if: always()`), sube las evidencias
   **solo si la higiene pasó** (nunca `.auth/`) y borra `.auth`.

Hay además una ejecución programada (`schedule`) con un solo juego (`vars.DEFAULT_GAME`, por defecto
`Pragmatic Play / Sweet Bonanza`). Todavía no se genera informe: solo los datos crudos y las evidencias.

### `Actualizar catálogo` (`.github/workflows/update-catalog.yml`)

Se ejecuta cada lunes o a mano. Hace el scrape y, si hay cambios, abre un PR que actualiza
`config/catalog/es.json` y los desplegables de `tests.yml`.

`GITHUB_TOKEN` no puede modificar workflows, así que necesita el secreto **`CATALOG_PAT`**: un token
fine-grained de este repo con permisos _Contents_, _Pull requests_ y _Workflows_ (lectura y escritura).
Sin él, el job falla con un mensaje claro y deja los archivos generados como artifact para commitearlos
a mano. También se puede ejecutar `python scripts/update_catalog.py` en local y commitear.

Si betsson.es bloquea las IP de GitHub, cambia `runs-on` a `self-hosted` en ambos workflows.

## Reglas de seguridad

Resumen; la referencia completa está en [CLAUDE.md §3](CLAUDE.md):

- **Ninguna credencial** en el repo, informes, capturas, trazas, vídeos ni logs. Solo variables de entorno.
- Las credenciales se representan como `***`; los errores nombran la variable, nunca el valor.
- El login ocurre en un contexto **sin vídeo ni traza**, y sus capturas enmascaran todos los campos.
- `.auth/` (sesión) nunca se sube y se borra al final del job.
- `tests/test_secret_hygiene.py` busca los valores `BETSSON_*` en `artifacts/` (también dentro de
  `trace.zip`). Se ejecuta siempre y **no se puede desactivar ni debilitar**.
- Nunca se intenta saltar CAPTCHA, 2FA, verificación por email ni sistemas anti-bot: se captura (enmascarado),
  se falla con _"Login bloqueado por verificación adicional"_ y se termina.
- Nunca se juega en modo demo cuando se pide Real Play.
