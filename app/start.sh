#!/bin/bash
# Start the server and the screen together; Ctrl+C stops both.
#
#   app/start.sh                       # Kanon v1.4.1 and JD2
#   app/start.sh --speaker PATH ...    # other speakers (same options as app_core.server)
#
# Then open http://127.0.0.1:5173 (several windows stay in sync).
# Ports: APP_SERVER_PORT (default 8765), APP_WEB_PORT (default 5173).
set -euo pipefail
APP=$(cd "$(dirname "$0")" && pwd)
R=$(dirname "$APP")

# Python: build-mac/py.sh of this checkout, else of the main checkout (worktrees).
PYSH=$R/build-mac/py.sh
if [ ! -x "$PYSH" ]; then
  MAIN=$(dirname "$(git -C "$R" rev-parse --path-format=absolute --git-common-dir)")
  PYSH=$MAIN/build-mac/py.sh
fi
# VTL: the library of this checkout when it is built.
[ -f "$R/build-mac/gui/libVocalTractLabApi.dylib" ] && export VTL_LIB=${VTL_LIB:-$R/build-mac/gui/libVocalTractLabApi.dylib}

export APP_SERVER_PORT=${APP_SERVER_PORT:-8765}
export APP_WEB_PORT=${APP_WEB_PORT:-5173}

ARGS=("$@")
if [ ${#ARGS[@]} -eq 0 ]; then
  ARGS=(--speaker "fulkhisa-kanon-v1-4-1=$R/speakers/fulkhisa-kanon/fulkhisa-kanon-v1-4-1.speaker"
        --speaker "JD2=$R/speakers/JD2.speaker")
fi

[ -d "$APP/web/node_modules" ] || (cd "$APP/web" && npm install)

cd "$APP"
bash "$PYSH" -m app_core.server --port "$APP_SERVER_PORT" "${ARGS[@]}" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
# Wait until the server answers; stop if it died.
until curl -s -o /dev/null "http://127.0.0.1:$APP_SERVER_PORT/api/project"; do
  kill -0 $SERVER 2>/dev/null || { echo "the server did not start" >&2; exit 1; }
  sleep 0.2
done
cd "$APP/web"
echo "screen: http://127.0.0.1:$APP_WEB_PORT"
npx vite
