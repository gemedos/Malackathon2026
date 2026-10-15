#!/usr/bin/env bash
# Abre Playwright codegen (equivalente a `playwright codegen https://www.betsson.es`) con las mismas
# opciones que los tests, para descubrir y confirmar los selectores de config/selectors/<mercado>.yaml.
# La URL, el idioma y la zona horaria se leen de config/markets/<mercado>.yaml.
#
#   ./scripts/inspect_site.sh                      # portada del mercado (MARKET, por defecto es)
#   ./scripts/inspect_site.sh "Pragmatic Play"     # página del proveedor
#
# AVISO: codegen muestra lo que tecleas. Si inicias sesión, no guardes el script generado
# ni hagas capturas del formulario: nunca deben acabar en el repositorio.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
read -r URL LOCALE TZ < <("$PY" - "${1:-}" <<'PYEOF'
import sys
sys.path.insert(0, "src")
from validator.config import current_market, load_market
from validator.urls import provider_url
m = load_market(current_market())
url = provider_url(m, sys.argv[1]) if sys.argv[1] else m.base_url
print(url, m.locale, m.timezone)
PYEOF
)

echo "Abriendo codegen en $URL ($LOCALE, $TZ)"
exec "$PY" -m playwright codegen \
  --target python \
  --viewport-size "1280,720" \
  --lang "$LOCALE" \
  --timezone "$TZ" \
  "$URL"
