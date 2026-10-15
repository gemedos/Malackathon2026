# Malackathon 2026 — BetssonGroup

Prueba de concepto que valida un juego de casino **como lo haría un jugador** en
[betsson.es](https://www.betsson.es): navega, inicia sesión, abre un juego de Pragmatic Play en **Real Play**
y valida los dos escenarios del reto **leyendo la pantalla** (OCR y visión), sin tocar el DOM del juego.

> Las reglas del proyecto están en [CLAUDE.md](CLAUDE.md) y son obligatorias.

> **¿Quieres ejecutarlo?** Sigue [HOW_TO_RUN.md](HOW_TO_RUN.md): `python run.py setup` una vez y después `python run.py`.


# Carpeta reports
Esta carpeta contiene el report con al menos un test fallido, además de la entrada que ocasiona dicho report, en la carpeta artifact

# Script make_report.py
Este script se encarga de generar un report en formato html (report.html) a partir de un fichero JSON (results.json). Para que este script funcione, la carpeta artifacts (generada por el programa encargado de entrar a la casa de apuestas), debe estar en el mismo nivel de directorio que este script. En otro caso, la línea 7 "SRC = sys.argv[1] if len(sys.argv) > 1 else "artifacts/es/results.json"", habría que modificarla por "SRC = sys.argv[1] if len(sys.argv) > 1 else "<nombreCarpeta>/artifacts/es/results.json"". Otro modo de usar este script es pasándo la ruta donde se encuentra el JSON (argumento 1) y dónde queremos que se guarde el report (argumento 2). 


# Diseño del Tester
Nuestra implementación está basada en la visión por computador. De forma que, el programa toma capturas de cada fase y a partir de esta, tomar una decisión. Es decir, el flujo para este programa es:
1. Iniciar el navegador (usando chromium) e ingresar en la casa de apuestas.
2. Inicia sesión.
3. Repite estos pasos para luego empezar a grabar la pantalla y así evitar que en la grabación se vea el usuario y contraseña.
4. Busca el juego.
5. Según la cuenta con la que haya sido iniciada (con o sin saldo), intentará hacer una tirada.
6. Genera el archivo JSON con todos los valores necesitados por los test ya capturados (esperado y recibido).

Luego, manualmente, hay que ejecutar make_report.py para que a partir del JSON, genere el report sobre los test del flujo (Véase make_report.py).

# Puesta en marcha rápida
Requisitos: Python 3.11+ y Tesseract OCR. El resto lo instala python run.py setup.

## Windows (PowerShell)
Instala Tesseract desde https://github.com/UB-Mannheim/tesseract/wiki (ruta por defecto C:\Program Files\Tesseract-OCR) y, desde la carpeta del proyecto:

```bash
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # solo si PowerShell bloquea el siguiente comando
.venv\Scripts\Activate.ps1
python run.py setup          # dependencias, Chromium, OCR en español y credenciales (.env)
python run.py test           # pruebas sin dinero real ni betsson.es
python run.py                # Escenarios 1 y 2 con DINERO REAL (Pragmatic Play / Bubble Up) + informe
```
## macOS / Linux

```
brew install tesseract tesseract-lang        # Linux: sudo apt install tesseract-ocr
python3 -m venv .venv && source .venv/bin/activate
python run.py setup
python run.py test
python run.py
```

# Calibración de juegos

Cada juego se lee por regiones de pantalla (balance, wager, payout, currency, reels, message, spin_search) expresadas como fracciones del iframe, más la plantilla del botón Spin. El orden de uso es:
1. config/games/<proveedor>/<juego>.yaml, si existe.
2. La calibración del proveedor (_default.yaml, validada con Pragmatic Play).
3. **Calibración automática**: si el HUD no coincide o el proveedor no tiene calibración, se calibra el juego en la propia sesión (sin apostar): se pulsan pantallas de inicio («CONTINUAR», «JUGAR»...), se localizan saldo, apuesta y premio por sus etiquetas o importes y se escribe el YAML del juego.
La calibración automática es una propuesta: el veredicto depende de los saldos antes y después del giro, así que una región mal puesta termina en INCONCLUSIVE, nunca en un PASS falso. Para revisarla a mano:

```bash
python run.py calibrate "NetEnt" "Dead West"           # captura el juego y propone config/games/netent/dead-west.yaml
python run.py calibrate "NetEnt" "Dead West" --reuse   # reutiliza las capturas ya hechas (sin abrir el navegador)
```
Deja calibration/<proveedor>/<juego>/annotated-auto.png (regiones y candidatos a botón Spin numerados). Comprueba que cada recuadro rodea su importe, que el Spin elegido es el botón correcto y, si lo es, pon calibrated: true. Para ajuste fino: python scripts/calibrate.py check --provider ... --game ... --image <captura>. Si el juego oculta el premio al perder, pon payout_empty_is_zero: true; para apostar la mínima, añade setup_clicks.

Límites conocidos: texto del HUD muy pequeño, botón Spin sin forma circular, pantallas previas de otros proveedores que no estén en config/selectors/es.yaml y mensajes de error en posiciones muy distintas pueden requerir ajuste manual.

### Malackathon2026
