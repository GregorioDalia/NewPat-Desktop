# Bundled IGV browser component

`igv.min.js` is the **unmodified IIFE bundle from `igv@3.8.9`**, obtained from
its npm distribution. CSS and CRAM decompression support are included in the
bundle. `manifest.json` records the upstream package integrity and SHA-256 of
all files retained here. No package manager, CDN or additional download is
needed to use IGV after installation.

The original IGV MIT license is `igv.LICENSE.txt`. The bundle retains upstream
license comments. `licenses/` additionally retains upstream notices and full
license texts for bundled components identified in the source or comments;
`licenses/sources.json` identifies each notice source. The `igv-utils` v1.8.4
package declares MIT but does not supply a separate license file at that tag;
its unmodified package metadata is retained. NIPAT's GPL does not replace any
of these third-party terms.

The NIPAT adapter is the adjacent `../igv-view.js`, maintained separately from
upstream code. It disables default genome downloads, online gene lookup,
query-string configuration and WebSocket control. It permits only same-origin
loopback URLs registered by the desktop application. BAM/CRAM and reference
files are read by byte range; their entire contents are not copied into the
JavaScript bridge. Remote sequence-analysis menu actions are removed from
viewer instances. The desktop host also applies a local-only network policy.

Tests in `tests/test_gui_igv.py` verify asset integrity and exercise the
adapter's local-resource checks, failure cleanup and session lifecycle using
a stub of IGV's public API. Native desktop rendering is a separate integration
check. View snapshots deliberately omit temporary resource capability URLs;
the application must save selected local source paths separately and register
them again before restoring a snapshot.
