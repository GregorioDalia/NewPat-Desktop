#!/bin/bash
set -euo pipefail

kit="$(cd "$(dirname "$0")" && pwd -P)"
if [[ "$(uname -s)" != Darwin ]] || [[ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null || true)" != 1 ]]; then
    echo "Questo kit richiede un Mac con chip Apple Silicon."
    exit 1
fi
os_version="$(/usr/bin/sw_vers -productVersion)"
if (( ${os_version%%.*} < 14 )); then
    echo "Per NewPat serve macOS 14 o successivo. Su questo Mac è installato macOS $os_version."
    exit 1
fi
if ! /usr/bin/xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang >/dev/null 2>&1; then
    echo "Apple mostrerà la richiesta per installare i Command Line Tools."
    echo "Completa l'installazione, poi riapri Prepara-NewPat.command."
    /usr/bin/xcode-select --install || true
    exit 1
fi

# mktemp creates private work directories. The files staged inside the installer
# must be readable after Apple's Installer assigns them to root.
umask 022
result="$(/usr/bin/mktemp -d "$HOME/Downloads/NewPat-0.9.8-arm64.XXXXXX")"
work="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/newpat-098.XXXXXX")"
exec > >(/usr/bin/tee "$result/preparazione.log") 2>&1
finish() {
    code=$?
    trap - EXIT
    /bin/rm -rf -- "$work"
    if (( code != 0 )); then
        echo "Preparazione interrotta. Dettagli in $result/preparazione.log"
    fi
    exit "$code"
}
trap finish EXIT

echo "Controllo i file del kit. La preparazione può richiedere alcuni minuti."
(cd "$kit" && /usr/bin/shasum -a 256 -c SHA256SUMS)
/usr/bin/tar -xzf "$kit/support/source.tar.gz" -C "$work"
/usr/bin/tar -xzf "$kit/support/python.tar.gz" -C "$work"
python="$work/python/bin/python3.12"
source_dir="$work/source"
manifest="$kit/support/assets/installer-manifest.json"
package_name="NIPAT-0.9.8-macos-arm64.pkg"
if [[ "$(/usr/bin/git -C "$source_dir" rev-parse HEAD)" != aec701f6f14bbd0f770dd79812b085be1e17096c ]]; then
    echo "I sorgenti non corrispondono alla build 0.9.8."
    exit 1
fi

echo "Preparo l'installer Apple Silicon con il motore scientifico della 0.9.8."
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
"$python" "$source_dir/scripts/build_macos_installer.py" \
    --project "$source_dir" --manifest "$manifest" --architecture arm64 \
    --python-archive "$kit/support/python.tar.gz" --lima-archive "$kit/support/lima.tar.gz" \
    --output "$work/output"

echo "Verifico il pacchetto e avvio un breve controllo della sua interfaccia sul Mac."
"$python" - "$work/output/macos-installer-build.json" <<'PY'
import json
from pathlib import Path
import sys

inventory = json.loads(Path(sys.argv[1]).read_text())["payload_inventory"]
app = "Applications/NewPat.app/Contents/"
for relative, required in (
    ("Info.plist", 0o004),
    ("Resources/app/.distribution/macos-manifest.json", 0o004),
    ("MacOS/NewPat", 0o005),
):
    if inventory[app + relative]["mode"] & required != required:
        raise SystemExit(f"Il pacchetto non concede i permessi necessari per aprire {relative}.")
PY
"$python" "$source_dir/scripts/verify_macos_package.py" \
    --package "$work/output/$package_name" --manifest "$manifest" \
    --report "$work/output/macos-package-verification.json"
mv "$work/output" "$result/verificato"
echo "Installer verificato: $result/verificato/$package_name"
echo "Segui le istruzioni di Installer, poi apri NewPat da Applicazioni."
/usr/bin/open "$result/verificato/$package_name" || echo "Apri il file .pkg dalla cartella indicata."
