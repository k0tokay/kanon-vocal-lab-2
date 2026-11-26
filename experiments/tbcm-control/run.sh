#!/bin/bash
# Python of the main checkout (build-mac/py.sh) with the API built in this checkout.
W=$(cd "$(dirname "$0")/../.." && pwd)
M=$(cd "$(git -C "$W" rev-parse --git-common-dir)/.." && pwd)
export VTL_LIB=${VTL_LIB:-$W/build-mac/gui/libVocalTractLabApi.dylib}
exec bash "$M/build-mac/py.sh" "$@"
