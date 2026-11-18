# NIPAT 0.9.1 Testing

This GUI prerelease followed 0.9.0. **0.8.99** remained stable. The changes concerned use of the application. The scientific calculations and R scripts were unchanged.

## Changes

- Windows testing installation guides users through preparation and launch, creates identifiable shortcuts and preserves preview experiments.
- The GUI starts with a NIPAT icon and application identity, without a separate console. Installation and maintenance still display their own messages.
- The initial progress bar was corrected. A continuous DNA animation, current phase and elapsed time provide feedback. Percentages appear when the engine can measure progress.
- After an abnormal exit, the app checks experiments still marked as running. Users can rerun an experiment or remove it from the list while preserving its files.
- IGV detects available indexes, checks formats, reports actionable errors, supports chromosome selection, synchronizes coordinates and provides zoom, overview and previous-view controls.
- Users can open BAMs saved with an experiment and jump to regions from result tables containing usable coordinates.

## Installing the preview

On Windows, download **NIPAT-0.9.1-Testing-installazione.zip** from [release v0.9.1](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.1). Before extracting, open the ZIP's **Properties**, select **Unblock** if available, then **Apply**. Extract the entire archive, run **INSTALLA-NIPAT-TESTING.cmd** and follow the preparation instructions. On completion the GUI opens and NIPAT Testing shortcuts are available.

Unblocking clears the internet-origin indicator for the selected archive. Smart App Control, Defender and other workstation policies remain active and can still restrict unsigned software.

Close NIPAT before updating. The testing installer recognizes a verified previous testing installation and preserves its working directories. It does not automatically select the stable installation as its destination. Starting the reused **NIPAT-Setup.exe** directly still selects the stable release. The Testing archive locates the preview installation directory. Initial downloads and prerequisite preparation may require internet access. Analyses and IGV with local files run locally.

For macOS and Ubuntu choose packages from the v0.9.1 release page. The `latest` links point to the stable release. Each package updates its platform installation.

## Verification and scope

Automated checks cover client regression, packaging, native GUI launch, experiment states and recognition of IGV files. The release includes the actual build reports and acceptance decision. The synthetic checks leave real samples and the user's Windows workstation to separate testing.

Removing a list entry preserves results and original files. Rerunning creates a new experiment from the beginning. IGV checks file types and basic consistency. Determining whether the biological reference is correct and every index is current requires separate evidence. See the [GUI guide](GUI.md).
