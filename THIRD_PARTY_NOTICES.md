# NewPat licensing and third-party notices

## Original NewPat material

The original NewPat source code, scripts and project documentation in this
repository are licensed under the **GNU General Public License, version 3 or,
at your option, any later version** (`GPL-3.0-or-later`), except where a file
or component carries its own notice. Copyright remains with the respective
authors and contributors.

NewPat is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

NewPat is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

The complete, unmodified license text is in [LICENSE](LICENSE). It was obtained
from <https://www.gnu.org/licenses/gpl-3.0.txt>.

The license permits academic and commercial use. Redistribution must comply
with its conditions, including the applicable source-code obligations.
Using NewPat does not transfer ownership of the user's input data or, merely
because they were produced with NewPat, place scientific results under the GPL.

## Scientific components included in the source tree

| Component | Upstream source | Included license and scope |
| --- | --- | --- |
| NEWPAT | <https://github.com/lpistacchia/NEWPAT> | [Upstream LICENSE](scientific/vendor/NEWPAT/LICENSE), containing the GNU GPL version 3 text. Includes the supplied SNPcall, prenatal CPI, postnatal CPI and Contamination files and accompanying examples. |
| DNPcall | <https://github.com/fravasini/DNPcall> | [Upstream LICENSE](scientific/vendor/DNPcall/LICENSE), containing the GNU GPL version 3 text. Includes the supplied DNPcall files and accompanying examples. |

These components retain their original authorship, license texts and notices.
NewPat uses the complete SNPcall 2.0 scientific core from NEWPAT commit
`ce59f4beeeec710b1b42d425cb87d7aad729f71d`; an unmodified copy is retained in
`tests/reference_r/2.0/SNPcall.R` as the differential-test reference. NewPat's
input adapters, resource scheduling and presentation changes are identified
separately from that upstream source.
The prenatal CPI update comes from NEWPAT commit
`eabff16fa475433ead4d9110a21bf3e330d8ccc6`, and the postnatal CPI update from
`97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4`. The latter snapshot also contains the
unchanged Contamination reference. Unmodified scripts for the three modules
are frozen in `tests/reference_r/NEWPAT_20261125`; operational copies add
validated configuration, shared execution budgets and readable exports.

The `GPL-3.0-or-later` grant for original NewPat material does not add an
"or later" permission to third-party files. Their own applicable terms govern
them.

[scientific/README.md](scientific/README.md) records the upstream revisions
and the integration of each component.
[scientific/SHA256SUMS](scientific/SHA256SUMS) identifies the exact scientific
files used by NewPat. Preserve these records when distributing a modified copy.

## Software supplied with the runtime

The desktop interface includes the following components:

- **igv.js 3.8.9:** the unmodified browser bundle from
  <https://github.com/igvteam/igv.js/releases/tag/v3.8.9>, distributed under
  the [MIT license](src/nipat/gui/web/vendor/igv.LICENSE.txt). The bundled
  dependency notices are preserved in
  [web/vendor/licenses](src/nipat/gui/web/vendor/licenses); the adjacent
  [manifest](src/nipat/gui/web/vendor/manifest.json) records provenance and
  digests. NewPat's integration adapter is separate from the upstream bundle.
- **Microsoft WebView2 SDK loader:** the x64 loader from the
  Microsoft.Web.WebView2 1.0.4314.35 NuGet package is included for Windows.
  The package's `.nuspec` declares its unchanged
  [LICENSE.txt](src/nipat/gui/native/windows/LICENSE.txt), containing the
  Microsoft BSD-style redistribution terms supplied with that SDK.
- **Microsoft WebView2 Evergreen Runtime bootstrap:** this official
  Microsoft installer is a separate component, governed by the
  **Microsoft Software License Terms for Microsoft Edge WebView2 Runtime**,
  shown by the download controls on the
  [official Runtime download page](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
  The SDK license above does not apply to the Runtime. Microsoft documents
  [packaging the bootstrapper with an application](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).
  NewPat's GPL does not relicense Microsoft binaries. The
  [dependency manifest](src/nipat/gui/native/windows/dependencies.json)
  records exact source locations, sizes and SHA-256 digests. The runtime
  bootstrap is used only when the Microsoft runtime is absent.
- **System GUI frameworks:** macOS uses Cocoa and WKWebView supplied by
  the operating system. Ubuntu uses GTK 3, WebKitGTK 4.1 and PyGObject
  installed as distribution packages, with their corresponding package
  licenses and notices. These frameworks are not vendored in NewPat source.

The Windows, Linux and macOS packages also contain software with its own
licenses. The NewPat license does not replace those licenses.

- **Python:** the Windows embedded distribution is obtained from python.org.
  Its license and third-party notices are included in that distribution and
  must remain with the extracted runtime.
- **Python on macOS:** the native CPython 3.12.16 distributions are supplied by
  [python-build-standalone](https://github.com/astral-sh/python-build-standalone),
  release `20261026`. Python retains its Python Software Foundation license and
  associated historical notices. The package preserves `python/lib/python3.12/LICENSE.txt`
  and the bundled pip dependency notices. The upstream build dependency notices
  are also retained, unmodified, in
  [installer/macos/licenses/python-build-standalone](installer/macos/licenses/python-build-standalone);
  `provenance.json` records the source archives and notice digests. The NewPat
  license does not replace the individual terms for OpenSSL, libffi, SQLite,
  compression libraries or other Python build dependencies.
- **Lima on macOS:** native Lima 2.2.1 binaries are supplied by
  [lima-vm/lima](https://github.com/lima-vm/lima), under the Apache License 2.0.
  The complete upstream distribution is retained, including
  `lima/share/doc/lima/LICENSE`, guest agents and their supplied notices.
  [installer/macos/dependencies.json](installer/macos/dependencies.json) records
  the exact architecture-specific Python and Lima archive hashes.
- **R, R packages, samtools and HTSlib:** the scientific image is assembled by
  [docker/scientific-runtime/Dockerfile](docker/scientific-runtime/Dockerfile).
  Each component retains its own terms. R package descriptions and their
  associated license files identify the package-specific conditions. The
  samtools release's notices are retained in the scientific image at
  `/usr/share/doc/nipat-samtools/samtools/LICENSE`,
  `/usr/share/doc/nipat-samtools/htslib/LICENSE`,
  `/usr/share/doc/nipat-samtools/htscodecs/LICENSE.md` and
  `/usr/share/doc/nipat-samtools/lz4/LICENSE` before its build sources are removed.
- **Debian packages and the dedicated Docker Engine:** the WSL filesystem is
  assembled by [installer/runtime/Dockerfile](installer/runtime/Dockerfile).
  Its package inventory is stored in `/usr/share/nipat/apt-versions.tsv`,
  package metadata in `/usr/share/nipat/docker-package-metadata.txt`, and
  provenance in `/etc/nipat-runtime.json`. Package notices are retained under
  `/usr/share/doc`; the exact engine's upstream LICENSE and NOTICE are also
  retained under `/usr/share/doc/docker-ce`.

This inventory describes the principal components; it is not a replacement
for the license and notice files of every dependency in a runtime image.

## Redistribution and release records

Distribute this notice, the root LICENSE and the original third-party license
files with the Windows installer, Ubuntu package and macOS installer. The release's source commit identifies
the matching NewPat source, including launcher and build scripts, at
<https://github.com/GregorioDalia/nipat-desktop>.

For binary runtime components, retain the notices for the exact distributed
versions and provide corresponding source wherever their licenses require it.
A component list or a Dockerfile alone does not replace that source. Maintain
source availability together with the release assets rather than relying on
temporary CI artifacts.
