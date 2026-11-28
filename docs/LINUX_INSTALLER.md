# Install NewPat on Ubuntu

The supported system is **Ubuntu 24.04 LTS on x86_64/amd64**. Download the `newpat-desktop_<version>_amd64.deb` package from the [stable release](https://github.com/GregorioDalia/NewPat-Desktop/releases/latest). The package contains the desktop client, documentation and the Linux image with R, samtools and the scientific dependencies. Its APT package name is `newpat-desktop`.

## Install and start

1. In a terminal, change to the directory containing the downloaded package. Run the following and enter the exact DEB filename shown in that directory.

   ```bash
   read -r -p "Downloaded DEB filename: " package
   sudo apt install "./$package"
   ```

2. Review the dependencies APT proposes. It uses the configured repositories to install Python 3.12, GTK/WebKit bindings, Docker Engine (`docker.io` or `docker-ce`) and Compose v2 (`docker-compose-v2` or `docker-compose-plugin`). Missing packages require internet access. APT handles dependencies for local packages. A graphical package manager can do this if it supports installation of local files.
3. Have the administrator start the system Docker daemon and authorize your regular account to access `/var/run/docker.sock`. Membership of the `docker` group confers root-equivalent privileges. After a group change, sign out and sign in again. Follow [Docker's Linux post-installation instructions](https://docs.docker.com/engine/install/linux-postinstall/).
4. Open **NewPat** from the applications menu or run `newpat` as your regular user. The first launch verifies the included archive, imports the image, checks the engine and runs the self-tests. Allow several minutes. Try **Environment and help → Open demo** for a first experiment with bundled data. Review its inputs and start the analysis. [Desktop guide](GUI.md)

Use a local system daemon with Linux AMD64 containers and ordinary UID mapping. Remote daemons, rootless Docker and `userns-remap` are outside this package's supported configuration. The installer leaves Docker configuration and account privileges to the administrator. Allow room for the installed application, expanded image, inputs, intermediates and results.

Subsequent launches reuse the verified local image and state. To repeat the complete preparation and self-tests, run `newpat --setup`. A failed preparation blocks analysis until the underlying issue is resolved.

## Commands and files

```bash
newpat --version
newpat --help
newpat dnp-call --help
newpat doctor --runtime
newpat self-test
newpat wizard
```

Help and version work without Docker. A `--dry-run` prepares the run description without testing runtime availability. `doctor --runtime` checks engine contracts. `self-test` checks the distributed examples. See the [user guide](USER_GUIDE.md) for inputs and workflows.

| Item | Default location |
| --- | --- |
| Application and scientific archive | `/opt/newpat-desktop` |
| Command | `/usr/bin/newpat` |
| Data and results | `~/.local/share/newpat-desktop/data`, `~/.local/share/newpat-desktop/runs` |
| Runtime state and setup log | `~/.local/state/newpat-desktop/state.json`, `~/.local/state/newpat-desktop/setup.log` |
| Menu preferences | `~/.config/newpat-desktop/preferences.json` |

Absolute `XDG_DATA_HOME`, `XDG_STATE_HOME` and `XDG_CONFIG_HOME` override the corresponding base directories. Keep samples and results in user-owned locations. Set defaults in the application or supply options before the CLI subcommand:

```bash
newpat --runs-dir "$HOME/newpat-results" contamination \
  --input "$HOME/samples/sample.txt" --panel "$HOME/panels/DNPpanel.txt"
```

Direct commands use explicit inputs. Guided sessions can also use saved preferences.

## Update and remove

**Check for updates** in `newpat wizard` downloads and verifies the DEB for the chosen channel. Confirm installation to close the client and open a system terminal. APT requires administrator authorization through Polkit. If a terminal or Polkit is unavailable, NewPat keeps the verified package and displays the APT command for the administrator. Alternatively, install the new DEB using the same `sudo apt install ./filename.deb` procedure.

Close active sessions before changing the package. APT updates application files and retains user data. On the next launch NewPat verifies the new application, manifest and image before starting analyses. An interrupted APT/dpkg transaction needs administrator attention. A preparation failure after APT completes requires repair of the new installation.

```bash
sudo apt remove newpat-desktop
```

Removal deletes the application and shortcut. Data, results, state, preferences, Docker images, daemon and account permissions remain.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot reach Docker or open its socket | Check service status and the current account's socket access with the administrator. |
| Unsupported daemon or platform | Check architecture, Docker socket, rootless mode and UID remapping. |
| Archive verification fails | Keep the setup log, verify the package checksum and reinstall the same verified build. |
| Another setup is running | Wait for it to finish before starting a second preparation. |
| Self-test fails | Keep the state file, setup log and affected run directories. Resolve the reported cause and repeat `newpat --setup`. |
| Scientific image has been removed | Launch NewPat again to restore it from the included archive. |
| An update stops midway | Keep APT output and the update handoff state under `${XDG_CACHE_HOME:-$HOME/.cache}/newpat-desktop/updates/handoff-*/state.json`. Check the ordinary setup log for subsequent runtime errors. |

Package checks cover APT installation, non-root execution, first launch, reinstallation and removal. A separate dependency check starts without Docker packages and verifies APT resolution. The [acceptance protocol](INSTALLER_ACCEPTANCE.md), [CI guide](CI_CD.md) and [validation record](VALIDATION.md) distinguish automated checks from testing on a physical Ubuntu desktop.
