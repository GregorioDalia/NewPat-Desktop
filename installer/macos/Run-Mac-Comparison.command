#!/bin/sh
set -eu
kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
resources='/Applications/NewPat.app/Contents/Resources'
if [ ! -r "$resources/app/scripts/benchmark_macos_candidate.py" ]; then
    echo "Install the NewPat Apple Silicon candidate from this folder first."
    exit 1
fi
exec "$resources/python/bin/python3.12" -I -B "$resources/app/scripts/benchmark_macos_candidate.py" --source-commit-file "$kit/source-commit"
