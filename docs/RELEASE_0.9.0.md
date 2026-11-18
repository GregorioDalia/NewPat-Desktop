# NIPAT 0.9.0 Preview

This prerelease introduced the graphical interface for testing. **0.8.99** remained on the stable update channel.

## Desktop application

- The NIPAT window has persistent navigation, Italian and English interfaces, neutral colors and a DNA animation that can be disabled in preferences.
- Users can select samples, choose DNP and SNP independently, add optional analyses, set parameters and review the experiment before execution.
- Parameter labels describe each value, range and applicable phase. A catalog displays constants and typeset formulas.
- Real analyses report status and progress and support controlled interruption.
- The experiment archive supports importing earlier directories, reusing settings, reading summaries, tables and PDFs, and copying original results.
- Bundled JavaScript dependencies provide integrated IGV for indexed local references, alignments and tracks. IGV Desktop is not required.
- The GUI provides access to execution settings, engine resources, maintenance and updates. The CLI and text menu remain available.

The GUI uses the 0.8.99 scientific engine and R algorithms, including the existing plans, input checks and execution modules.

## Installing the preview

On Windows, download **NIPAT-0.9.0-Testing-installazione.zip** from [release v0.9.0](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.0), extract it and run **INSTALLA-NIPAT-TESTING.cmd**. The default preview directory is separate from the normal desktop installation. **NIPAT-0.9.0-Windows-completo.zip** is also available.

The setup EXE reuses the 0.8.99 bootstrap. Direct launch selects the stable release. The testing installer selects 0.9.0 explicitly and verifies package sizes and SHA-256 digests. The advanced `-UseSetup` option replaces the existing desktop installation and requires an explicit choice.

On macOS and Ubuntu use the v0.9.0 release packages, which update their platform installation. The `latest` links point to the stable release. On Windows, missing Microsoft WebView2 components are prepared automatically using an internet connection. Once the engine and data are ready, analysis and local-file IGV can run offline.

## Scope of verification

Release checks cover the GUI, local transport, packages and launch through native components. The release attaches build and acceptance evidence and retains scientific engine qualification under the 0.8.99 reuse rules. The preview enables testing with real data and workstations. Windows warnings and execution policies depend on the workstation. This release introduced no NIPAT signing certificate. See the [GUI guide](GUI.md) for the workflow and limitations.
