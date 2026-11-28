#!/bin/sh
set -eu
kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
resources='/Applications/NewPat.app/Contents/Resources'
if [ ! -x "$resources/python/bin/python3.12" ]; then
    echo "Installare NewPat 0.9.99 per Mac Apple Silicon, poi riaprire Mini-Test-NewPat.command."
    exit 1
fi
set -- --project "$resources/app"
if [ -f "$kit/source-commit" ]; then
    set -- "$@" --source-commit-file "$kit/source-commit"
fi
exec "$resources/python/bin/python3.12" -I -B "$kit/mini_suite_macos.py" "$@"
