# GitHub Actions con salida por España

betsson.es solo atiende conexiones desde España (requisito DGOJ) y los runners de GitHub (`ubuntu-latest`) están
en EE. UU., así que `tests.yml`, `scenarios.yml` y `update-catalog.yml` se quedan bloqueados en CI. Este documento
explica los workflows que lo resuelven **sin tocar el código del validador**: el tráfico sale por España a nivel
de red (Chromium, DNS y el iframe de Pragmatic van todos por la misma IP española).

> No es una evasión: si aparece CAPTCHA, 2FA o un reto del WAF, el test falla igual que antes
> (`LoginBlockedError`, CLAUDE.md §3). Confirma con los mentores de Betsson que la salida elegida es aceptable
> o pídeles que autoricen la IP.

## Workflows

| Workflow | Archivo | Para qué |
| --- | --- | --- |
| **Betsson ES (salida por España)** | `.github/workflows/betsson-es.yml` | Punto de entrada: cualquier proveedor y juego del catálogo, en modo navegación, escenarios o completo |
| **Actualizar catálogo (salida por España)** | `.github/workflows/catalog-es.yml` | Scrape semanal del catálogo + desplegables de `tests.yml` y `betsson-es.yml` (PR con `CATALOG_PAT`) |

**Actions → Betsson ES (salida por España) → Run workflow**:

| Input | Valores |
| --- | --- |
| `provider` | los 44 proveedores del catálogo |
| `game` | `(todos los juegos del proveedor)` o `Proveedor / Juego` (2.132 tragaperras); si eliges juego, manda su proveedor |
| `mode` | `navegacion` (login + juego en Real Play, sin spins, en lotes) · `escenarios` (1 y 2 con dinero real) · `completo` (navegación y, si va bien, escenarios) |
| `egress` | `auto` (= `vars.EGRESS_MODE`, por defecto `self-hosted`) · `self-hosted` · `tailscale` · `wireguard` · `none` |
| `chunk_size` | juegos por lote en navegación (20) |

Reglas que aplica el job `Planificar` (`scripts/ci/plan_run.py`) **antes** de abrir betsson.es:

- Los escenarios con dinero real solo se ejecutan sobre **un** juego concreto; con "(todos…)" el workflow se detiene.
- Si el juego no tiene calibración (`config/games/<proveedor>/`), avisa: el escenario saldrá INCONCLUSIVE, nunca PASS.
  Hoy solo está calibrado Pragmatic Play (`_default.yaml`). La navegación funciona con todos los proveedores.

Cada job que abre betsson.es hace: salida por España → dependencias → `scripts/ci/geo_check.py` → pruebas →
informe → test de higiene (`if: always()`) → artifact **solo si la higiene pasó** → cierre del túnel → `rm -rf .auth`.

## Comprobación previa (`scripts/ci/geo_check.py`)

1. Pregunta el país de salida a varios servicios (`config/ci/geo.yaml`); solo reciben el código de país, la IP no
   aparece en los logs. Basta con que responda uno; si alguno dice otro país, falla.
2. Abre la portada de betsson.es con el mismo Chromium y contexto que los tests y clasifica la respuesta:
   OK, bloqueo geográfico/WAF (403/451 o textos de "no disponible en tu país") o verificación anti-bot.
3. Escribe el resultado en el resumen del job. Códigos: `0` OK, `1` bloqueado, `2` sin servicios de geolocalización.

Así un runner mal configurado falla en un minuto con un mensaje claro, en lugar de a los 45 con un timeout de selector.

```bash
python scripts/ci/geo_check.py                 # en local (desde España debe dar OK)
python scripts/ci/geo_check.py --no-site-probe # solo el país
```

## Opción A: runner propio en España (`self-hosted`, recomendada)

El tráfico sale de verdad desde España. Sirve un portátil del equipo o un VPS con IP española (Linux x64).

1. **Settings → Actions → Runners → New self-hosted runner** y sigue los pasos. Al configurarlo añade la etiqueta `betsson-es`:
   `./config.sh --url https://github.com/<org>/<repo> --token <token> --labels betsson-es`
2. Instala una vez las dependencias del sistema (el workflow no usa `sudo` si ya están):
   ```bash
   sudo apt-get install -y tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng python3.12 python3.12-venv
   python3 -m playwright install-deps chromium
   ```
3. Arranca el runner (`./run.sh` o `sudo ./svc.sh install && sudo ./svc.sh start`).
4. Opcional: variable `ES_RUNNER_LABELS` si usas otras etiquetas, p. ej. `["self-hosted","linux","madrid"]`.

El runner persiste entre ejecuciones: el workflow borra `artifacts/`, `.auth/` y `calibration/` al empezar y al terminar.
Usa un repositorio privado o restringe los runners propios: un PR de un fork podría ejecutar código en esa máquina.

### Runner propio en Windows

Los workflows usan `shell: bash`, que en Windows es el Git Bash de Git for Windows. Una vez:

1. **Tesseract** con español: `winget install --id UB-Mannheim.TesseractOCR`; copia
   [`spa.traineddata`](https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata) a
   `C:\Program Files\Tesseract-OCR\tessdata\` y añade `C:\Program Files\Tesseract-OCR` al **PATH del sistema**.
   Comprueba en una consola nueva: `tesseract --list-langs` (debe listar `eng` y `spa`).
2. **Python**: `actions/setup-python` instala 3.12 en la caché del runner, lo que en Windows necesita permisos de
   administrador: arranca el runner como administrador (o como servicio con una cuenta administradora).
3. Reinicia el runner después de cambiar el PATH (lo lee al arrancar).

## Opción B: nodo de salida Tailscale en España (`tailscale`)

Corre en `ubuntu-latest` y sale por una máquina de la tailnet que esté en España.

1. En la máquina española: `sudo tailscale up --advertise-exit-node` y aprueba **Use as exit node** en la consola de admin.
2. En la política de la tailnet (ACL) crea la etiqueta `tag:ci` y permite que `tag:ci` use el exit node
   (`"autogroup:internet:*"`).
3. **Settings → OAuth clients** de Tailscale: cliente con permiso de escritura en *Devices* y la etiqueta `tag:ci`.
4. Secretos del repo: `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` y `TS_EXIT_NODE` (nombre o IP 100.x del nodo).

El runner entra como nodo efímero, desactiva IPv6 para que nada rodee el túnel y sale de la tailnet al terminar.

## Opción C: WireGuard a un servidor en España (`wireguard`)

1. Un servidor WireGuard en España (p. ej. un VPS) con un peer para CI.
2. Secreto `WG_CONFIG` con el `wg0.conf` completo del peer (`[Interface]` con `PrivateKey`, `Address`, `DNS`;
   `[Peer]` con `AllowedIPs = 0.0.0.0/0`).

El workflow lo escribe en `/etc/wireguard/wg-es.conf` (permisos 600), levanta el túnel y lo borra al terminar.
⚠️ Un VPN comercial puede incumplir los términos de Betsson: pide autorización a los mentores antes de usarlo.

## Variables y secretos

| Nombre | Tipo | Uso |
| --- | --- | --- |
| `BETSSON_ES_FUNDED_USER` / `_PASS`, `BETSSON_ES_EMPTY_USER` / `_PASS` | secreto | cuentas de prueba (igual que antes) |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `TS_EXIT_NODE` | secreto | solo `egress=tailscale` |
| `WG_CONFIG` | secreto | solo `egress=wireguard` |
| `CATALOG_PAT` | secreto | PR del catálogo (`catalog-es.yml`) |
| `EGRESS_MODE` | variable | salida por defecto (`auto` y ejecuciones programadas); si no existe, `self-hosted` |
| `ES_RUNNER_LABELS` | variable | etiquetas del runner propio en JSON; por defecto `["self-hosted","betsson-es"]` |
| `DEFAULT_PROVIDER`, `DEFAULT_GAME` | variable | ejecución programada (por defecto `Pragmatic Play / Sweet Bonanza`) |
| `SCHEDULE_MODE` | variable | modo de la ejecución programada (por defecto `completo`) |

```bash
gh secret set TS_OAUTH_CLIENT_ID     # pide el valor sin dejarlo en el historial
gh secret set WG_CONFIG < wg0.conf
gh variable set EGRESS_MODE --body tailscale
```

## Desplegables

GitHub solo admite opciones estáticas en `workflow_dispatch`. Las de `betsson-es.yml` se generan desde
`config/catalog/es.json` con el mismo renderizador que `tests.yml`:

```bash
python scripts/ci/render_dropdowns.py          # regenera
python scripts/ci/render_dropdowns.py --check  # 1 si está desactualizado
```

`catalog-es.yml` lo hace solo; `tests/test_ci_plan.py` falla si el workflow y el catálogo no coinciden.

## Problemas frecuentes

| Mensaje | Causa | Solución |
| --- | --- | --- |
| `La salida a internet no es ES: detectado US` | sin túnel o túnel caído | revisa `egress` y los secretos de la opción elegida |
| `egress=self-hosted pero el job corre en un runner de GitHub` | etiquetas que no coinciden | `ES_RUNNER_LABELS` o etiqueta `es` en el runner |
| El job queda en *Queued* | ningún runner propio en línea con esas etiquetas | arranca el runner |
| `El nodo de salida de Tailscale no está en línea` | máquina apagada o exit node sin aprobar | enciéndela y apruébalo en la consola |
| `betsson.es bloquea esta conexión (HTTP 403…)` | IP de datacenter vetada por el WAF aunque sea española | usa una IP residencial (runner propio/Tailscale en casa) o pide autorización a Betsson |
| `verificación anti-bot/CAPTCHA` | reto del WAF | no se salta: coordina con los mentores |
| `Los escenarios con dinero real se ejecutan sobre UN juego` | modo escenarios con "(todos…)" | elige un juego concreto |
