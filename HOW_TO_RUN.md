# HOW TO RUN — Betsson Intelligent Game Validation

Guía para ejecutar la prueba completa desde cero. Tiempo estimado: 10 min de instalación y ~5 min por ejecución.

La prueba abre betsson.es en Chromium, inicia sesión, entra en un juego en **Real Play**, lee la pantalla del juego
(OCR y visión, sin tocar el DOM del juego), hace **un Spin** y valida:

| Escenario | Cuenta | Qué comprueba |
| --- | --- | --- |
| 1 — Spin completado | con saldo | el Spin se hace, la apuesta, el premio y el saldo cuadran (`saldo antes − apuesta + premio = saldo después`) tanto en el juego como en la cabecera de Betsson |
| 2 — Saldo insuficiente | sin saldo | con 0 € el juego avisa de saldo insuficiente y no hay ningún Spin |

> **Aviso:** los escenarios juegan con **dinero real** (una apuesta mínima por escenario). Usa solo las cuentas de prueba.

## 1. Requisitos

- **Python 3.11 o superior** (`python --version`).
- **Tesseract OCR** (motor de OCR). Instálalo antes de nada:
  - Windows: instalador de <https://github.com/UB-Mannheim/tesseract/wiki> (ruta por defecto `C:\Program Files\Tesseract-OCR`).
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`
- Conexión a internet y las **credenciales de las dos cuentas de prueba** (con saldo y sin saldo).

## 2. Instalación (una sola vez)

Desde la carpeta del proyecto:

```powershell
# Windows (PowerShell)
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass     # solo si PowerShell bloquea el siguiente comando
.venv\Scripts\Activate.ps1
python run.py setup
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
python run.py setup
```

`python run.py setup` hace todo lo demás: instala las dependencias de Python, descarga Chromium, descarga el
idioma español del OCR y te pide las cuatro credenciales (usuario y contraseña de cada cuenta). Se guardan solo en
el archivo `.env`, que está en `.gitignore` y **nunca se sube a git**. Al terminar dice «Todo listo».

## 3. Ejecutar la prueba

```
python run.py
```

Eso es todo: ejecuta los escenarios 1 y 2 con **Pragmatic Play / Bubble Up**, con el navegador visible, y al
terminar genera el informe. **No cierres ni toques las ventanas del navegador mientras corre.**

Variantes:

| Comando | Qué hace |
| --- | --- |
| `python run.py -s 1` | solo el escenario 1 (cuenta con saldo) |
| `python run.py -s 2` | solo el escenario 2 (cuenta sin saldo) |
| `python run.py --headless` | sin ventana de navegador |
| `python run.py "Pragmatic Play" "Gates of Olympus"` | otro juego del proveedor (ver «Otros juegos») |
| `python run.py test` | pruebas **sin dinero real** ni betsson.es (visión + un juego falso local) |
| `python run.py inspect "Pragmatic Play" "Bubble Up"` | abre el juego **sin apostar** y lista los diálogos/botones visibles (útil si algo no se detecta) |
| `python run.py clean` | borra evidencias locales (`artifacts/`, `.auth/`) |

Cada ejecución borra las evidencias de la anterior (usa `--keep` para conservarlas).

## 4. Qué ocurre durante la prueba

1. Login con la cuenta del escenario (ventana sin vídeo ni traza, para no grabar la contraseña). Después se abre
   una ventana nueva con la sesión ya iniciada: es normal ver cerrarse y abrirse el navegador.
2. Página del proveedor → tarjeta del juego → **Real Play**.
3. Pantallas previas de la regulación española, resueltas solas: aviso de sesión de juego, límites de tiempo y
   gasto, panel de torneos.
4. Pantalla de carga del juego (se pulsa su Spin) y lectura del HUD: crédito, apuesta y moneda.
5. Se abre una **segunda pestaña (el lobby de Betsson)** solo para leer el saldo de la cuenta antes y después, porque
   la página del juego no muestra la cifra.
6. **Un Spin**, espera a que termine y lectura de premio y saldos con varias lecturas coincidentes.
7. Veredicto por escenario: **PASS**, **FAIL** o **INCONCLUSIVE** (si no se puede leer con certeza nunca se da PASS).

## 5. Dónde ver el resultado

Al terminar se imprime un **RESUMEN** en la terminal con el veredicto de cada escenario y los checks que no pasaron.
Los detalles están en `artifacts/es/`:

| Archivo | Contenido |
| --- | --- |
| `report.html` / `report.txt` | informe de la ejecución, generado por `scripts/make_report.py` (`python scripts/make_report.py` lo regenera) |
| `results.json` | cada check con su estado, detalle y evidencia |
| `run.log` | registro paso a paso (empieza aquí si algo falla) |
| `<proveedor>/<juego>/<escenario>/video.webm` | vídeo de la prueba |
| `<proveedor>/<juego>/<escenario>/vision/` | recortes que leyó el OCR y capturas anotadas |
| `<proveedor>/<juego>/<escenario>/trace.zip` | traza de acciones (`python -m playwright show-trace trace.zip`) |

## 6. Problemas frecuentes

| Síntoma | Solución |
| --- | --- |
| `No se puede empezar: …` | la propia línea indica qué falta; casi siempre `python run.py setup` |
| `Activate.ps1` bloqueado en PowerShell | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y repetir |
| `Tesseract no está instalado` | instálalo (paso 1) y repite `python run.py setup`; si está en otra ruta, añade `TESSERACT_CMD=<ruta>` a `.env` |
| Una pantalla nueva tapa el juego | se añade en `config/selectors/es.yaml`, sección `pregame` (ver `docs/MAPA.md`) |
| Resultado INCONCLUSIVE | no es un fallo del juego: algo no se pudo leer con certeza; revisa `vision/` y el vídeo |

## 7. Otros juegos y proveedores

El flujo es general y **se calibra solo**: `python run.py "<proveedor>" "<juego>"` funciona con cualquier juego.

1. Si el juego tiene su YAML (`config/games/<proveedor>/<juego>.yaml`), se usa.
2. Si no, se prueba la calibración del proveedor (`_default.yaml`, validada con Pragmatic Play).
3. Si el HUD no coincide, o el proveedor no tiene calibración, **el programa calibra el juego en esa misma sesión**
   (sin apostar): pulsa pantallas de inicio («CONTINUAR», «JUGAR»...), localiza saldo, apuesta y premio en pantalla,
   escribe el YAML del juego y sigue con las pruebas. La siguiente ejecución ya lo reutiliza.

La calibración automática es una propuesta: los saldos se siguen verificando después del giro, así que una región mal
puesta acaba en INCONCLUSIVE y nunca en un PASS falso. Para revisarla a mano:
`python run.py calibrate "<proveedor>" "<juego>"` (deja `calibration/<proveedor>/<juego>/annotated-auto.png` con las
regiones y los posibles botones Spin; `--reuse` reutiliza las capturas ya hechas). Límites conocidos: texto del HUD
muy pequeño, botón Spin sin forma circular y mensajes de error en posiciones muy distintas pueden requerir ajuste manual.

## 8. Estructura del código

Mapa de qué archivo hace cada paso y qué tocar cuando algo falla: [docs/MAPA.md](docs/MAPA.md).
Reglas del proyecto (visión sobre DOM, sin adivinar valores, un Spin por escenario): [CLAUDE.md](CLAUDE.md).

## 9. Seguridad

- Las credenciales viven solo en `.env` (ignorado por git). Nunca se escriben en el log, capturas ni informes.
- `run.py` comprueba al final que no hay credenciales en `artifacts/`.
- Antes de compartir la carpeta, ejecuta `python run.py clean`.
