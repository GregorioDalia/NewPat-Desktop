NewPat for Windows — complete ZIP

1. For a published release, download the complete Windows ZIP from its Assets.
   For an Actions review build, extract the artifact first and find the inner
   NewPat-<version>-Windows-complete.zip. Extract all files from that inner ZIP into
   a permanent folder on a local fixed drive.
2. As a regular Windows user, double-click 1_INSTALL.cmd.
3. When preparation finishes, NewPat opens. Next time, open NewPat\NewPat.lnk
   inside the extracted folder. This shortcut opens the app with its own icon.

For a first experiment, choose Environment and help > Open demo. Review the
three simulated samples and start the analysis. The expected results and
Italian instructions are in app\docs\QUICKSTART_IT.md.

For an upgrade from 0.9.9, extract to a fresh directory and run the included
install-zip.ps1 with -InstallRoot pointing to your existing NewPat folder.
See app\docs\WINDOWS_INSTALLER.md for the complete PowerShell command.
Opening 1_INSTALL.cmd in an unrelated fresh folder creates a new installation.

The complete ZIP includes Python 3.12.10, the WSL filesystem and the scientific
runtime. Windows may need internet access, administrator approval or a restart
to install or update Microsoft's WSL components. If you restart, open the same
NewPat\NewPat.lnk shortcut to resume preparation with the cached files.

Keep the installed NewPat folder at its original location. WSL registers it on
this computer. It contains the application, WSL filesystem, cache, input data
(NewPat\data) and results (NewPat\runs). After successful preparation, you can
remove the downloaded ZIP and the initially extracted app and assets folders.
Updates from the app use the complete ZIP and preserve the installed folder.
The classic EXE installation has a separate data directory.

If Windows blocks a file

Download SHA256SUMS from the same official release. In PowerShell, run
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\path\to\your-downloaded.zip'
and compare the hash to the line for the exact ZIP filename. If the values
differ, discard the download and obtain a fresh copy from the release.

For a review build, compare the inner ZIP with the sha256 and file entries
in windows-zip-build.json from the same Actions run.

If Windows still blocks installation, note the exact file named in the
dialog and the message. For a prepared installation, keep the setup log.
The Windows installation guide on GitHub explains the available installation
methods and how to collect diagnostic information:

https://github.com/GregorioDalia/NewPat-Desktop/blob/main/docs/WINDOWS_INSTALLER.md
