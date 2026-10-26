#!/usr/bin/env bash
# Abre Chrome visual em DISPLAY virtual Linux. Faça o 2FA manualmente.
# DevTools fica restrito a 127.0.0.1:9222. Nunca abra essa porta na internet.
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${SANTANDER_CHROME_PROFILE:-$ROOT/private/chrome-profile}"
mkdir -p "$PROFILE"
chmod 700 "$PROFILE"

if ! pgrep -f "Xvfb ${DISPLAY} " >/dev/null 2>&1; then
  echo "Iniciando tela virtual em ${DISPLAY}..."
  Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp > /dev/null 2>&1 &
  sleep 1
fi

if command -v google-chrome-stable >/dev/null 2>&1; then
  CHROME=google-chrome-stable
elif command -v google-chrome >/dev/null 2>&1; then
  CHROME=google-chrome
elif command -v chromium >/dev/null 2>&1; then
  CHROME=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME=chromium-browser
else
  echo 'Chrome/Chromium não encontrado. Instale um navegador compatível.' >&2
  exit 1
fi

exec "$CHROME" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  'https://www.parceirosantander.com.br/spa-base/'
