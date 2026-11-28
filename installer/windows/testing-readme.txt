NewPat for Windows — testing package

1. Extract the entire testing ZIP to a folder.
2. As a regular Windows user, double-click INSTALL-NewPat-Testing.cmd.
3. Wait for preparation to finish. NewPat opens automatically.

For subsequent sessions open NewPat Testing on the desktop or in the Start
menu. If Windows requires a restart, the same shortcut resumes preparation
and opens the app. Opening the original CMD file again also starts an
installation it already recognizes.

The testing entry point downloads the version named in testing-release.json
and verifies its size and SHA-256 hash. Its default installation directory is
%LOCALAPPDATA%\NewPat-Testing\NewPat. An existing recognized testing installation
may be reused. Keep its directory in place; it contains your preferences,
experiments, data, results and runtime. The default testing installation is
separate from the stable desktop installation.

An internet connection is required for download. For a first experiment,
choose Environment and help > Open demo. Review the three simulated samples,
then start the analysis. Their reference and panels are included. Open the
IGV viewer inside NewPat to inspect alignments.

If Windows blocks a file, verify the SHA-256 of the downloaded ZIP against
the entry for that exact filename in SHA256SUMS on the official release page.
Record the file named in the dialog and its message if the block persists.
The Windows guide describes installation and diagnostics:

https://github.com/GregorioDalia/NewPat-Desktop/blob/main/docs/WINDOWS_INSTALLER.md

Maintainers can explicitly target the existing desktop installation with the
-UseSetup option of install-testing.ps1. This installs the verified testing
payload through the setup program. Launching NewPat-Setup.exe on its own
selects the published stable version.
