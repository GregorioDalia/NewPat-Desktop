"""Verify bundled GUI dependencies and, on Windows, Microsoft's Authenticode signatures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

EXPECTED_FILES = {"x64/WebView2Loader.dll", "x64/MicrosoftEdgeWebview2Setup.exe", "LICENSE.txt"}


def verify(root: Path, *, signatures: bool = False) -> dict:
    root = root.resolve()
    directory = root / "src/nipat/gui/native/windows"
    manifest = json.loads((directory / "dependencies.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("sdk", {}).get("name") != "Microsoft.Web.WebView2":
        raise ValueError("Invalid native GUI dependency manifest")
    entries = manifest.get("files", [])
    if len(entries) != len(EXPECTED_FILES) or {entry.get("path") for entry in entries} != EXPECTED_FILES:
        raise ValueError("Unexpected native GUI dependency inventory")
    files = []
    for entry in entries:
        path = directory / entry["path"]
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or not path.is_file():
            raise ValueError("Missing or redirected native GUI dependency")
        raw = path.read_bytes()
        if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Native GUI dependency bytes do not match their pinned provenance")
        if path.suffix in {".dll", ".exe"}:
            if not raw.startswith(b"MZ"):
                raise ValueError("Invalid Windows GUI dependency format")
            files.append(path)
    observations = []
    if signatures:
        if os.name != "nt":
            raise ValueError("Authenticode signatures must be checked on Windows")
        # Names are JSON data in a private environment variable, never shell source.
        command = r'''$ErrorActionPreference='Stop'
$items = @(ConvertFrom-Json $env:NIPAT_GUI_SIGNATURE_INPUT)
@($items | ForEach-Object {
  $s = Get-AuthenticodeSignature -LiteralPath $_
  if ($s.Status -ne 'Valid' -or $null -eq $s.SignerCertificate -or
      $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
    throw ('Official Microsoft GUI dependency has an invalid signature: ' + $_)
  }
  [pscustomobject]@{name=[IO.Path]::GetFileName($_);status=[string]$s.Status;
    subject=$s.SignerCertificate.Subject;thumbprint=$s.SignerCertificate.Thumbprint}
}) | ConvertTo-Json -Compress
'''
        environment = dict(os.environ, NIPAT_GUI_SIGNATURE_INPUT=json.dumps([str(path) for path in files]))
        result = subprocess.run([
            os.path.join(os.environ["SystemRoot"], "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
            "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command,
        ], env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if result.returncode:
            raise ValueError("Microsoft GUI dependency signature check failed: " + result.stderr.strip())
        observations = json.loads(result.stdout.lstrip("\ufeff"))
        if not isinstance(observations, list) or len(observations) != 2:
            raise ValueError("Incomplete GUI signature observations")
    return {"schema_version": 1, "status": "passed", "sdk": manifest["sdk"]["version"],
            "files": entries, "authenticode": observations,
            "authenticode_checked": signatures, "smart_app_control": "not-performed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--signatures", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.project, signatures=args.signatures)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: GUI dependency bytes" + (" and Microsoft Authenticode signatures" if args.signatures else ""))


if __name__ == "__main__":
    main()
