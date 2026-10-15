#!/usr/bin/env bash
# Instala el driver de playwright-go y Chromium.
# El instalador oficial descarga el driver de un CDN retirado (404), así que se monta a mano:
# Node del sistema + paquete npm playwright-core de la misma versión que playwright-go.
set -euo pipefail
VERSION=1.57.0
GO_PKG=github.com/playwright-community/playwright-go/cmd/playwright@v0.5700.1
case "$(uname)" in
  Darwin) CACHE="$HOME/Library/Caches/ms-playwright-go/$VERSION" ;;
  *) CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/ms-playwright-go/$VERSION" ;;
esac
mkdir -p "$CACHE"
if [ ! -f "$CACHE/package/cli.js" ]; then
  (cd "$CACHE" && npm pack "playwright-core@$VERSION" --silent >/dev/null && tar xzf "playwright-core-$VERSION.tgz" && rm "playwright-core-$VERSION.tgz")
fi
ln -sf "$(command -v node)" "$CACHE/node"
WITH_DEPS=""
if [ "$(uname)" = "Linux" ]; then WITH_DEPS="--with-deps"; fi
go run "$GO_PKG" install $WITH_DEPS chromium
