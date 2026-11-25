# Continuous integration and release builds

The repository separates source verification, installer construction and publication. A green source CI run identifies the checks that passed for that revision. Release acceptance and verification bind the distributed packages to their source and scientific image.

| Workflow | Trigger | Result |
| --- | --- | --- |
| [CI](../.github/workflows/ci.yml) | Pull request, push to `main`, or manual dispatch | Required checks for the changed files, with dedicated Linux jobs for documentation and release acceptance |
| [Installers (review build)](../.github/workflows/windows-installer.yml) | Manual dispatch on a reviewed release revision | Full installer set and its qualification by default, or a Windows ZIP for local testing on request |
| [Prepare or publish verified release](../.github/workflows/publish-windows-release.yml) | Manual dispatch on `main` | Verified draft, publication of a verified draft, or combined preparation and publication |
| [Publish accepted release](https://github.com/GregorioDalia/nipat-desktop/blob/main/.github/workflows/publish-accepted-release.yml) | Successful qualifying CI push on `main` | Selection of acceptance-only changes and publication of the identified accepted build |
| [Published runtime security report](../.github/workflows/security-monitoring.yml) | Scheduled or manual dispatch | Inventory and findings for published images |

## Source verification

CI checks a development branch when it has an open pull request. Each update evaluates the full difference between the PR base and the proposed merge. A new commit can replace an earlier CI run on the same PR. After integration, each push to `main` gets its own run for the full interval from the previous main revision to the new one. Two consecutive merges can therefore finish independently. The `required` check enforces the jobs selected for each revision.

| Example change | Checks selected |
| --- | --- |
| Desktop stylesheet, web wordmark or translations | Linux client and browser tests, native Windows and macOS client checks |
| Playwright test dependency (`.github/gui-test-requirements.txt`) | Linux browser interactions and focused Windows and macOS client checks |
| Desktop reference registration, FASTA download or browser application logic | Client checks plus the DNP/SNP synthetic workflow |
| Caller, scientific scripts, analysis plan, scheduler or runtime used by the calculations | Full scientific qualification, plus other affected layers |
| An edit to a recognized guide | Linux documentation checks |
| A new guide added to the installer file list (`distribution-files.txt`) | Linux and Windows checks, plus packaging checks |
| An acceptance record only | Linux acceptance verification and the required gate |
| Recognized guides and acceptance records together | Linux documentation and acceptance checks, with automatic publication reserved for an acceptance-only push to `main` |

The classifier combines requirements for mixed changes. A graphical change added to a PR that already changes an algorithm still requires the scientific checks. A manual CI run selects all integration layers. Installer construction is a separate manual operation.

When a change consists entirely of recognized guides, CI runs the `documentation` job on Linux. It checks repository links and heading anchors, parses CLI examples in the current user guides, validates the documented workflow plan and compares shipping text with the contents of small archives created by the Windows package builders. Changes to `LICENSE` or `THIRD_PARTY_NOTICES.md` trigger scientific qualification. CI also checks both files inside the built image against their source hashes.

An unavailable comparison or an unfamiliar workflow change receives conservative coverage. Changes to core CI, its selector or installer construction retain applicable integration levels. Changes limited to the manual publisher activate its fast and packaging checks. Changes to automatic publication select the complete integration matrix. A simultaneous scientific change requires scientific checks.

A change limited to `.github/release-acceptance/vVERSION.json` uses `acceptance` and `required` on Linux. The job fetches bounded textual evidence to verify the build, source, completed platform jobs, four package digests, common manifest, historical baseline and scientific reports. A mixed change checks the affected acceptance records alongside the applicable source checks. Missing or mismatched records fail verification.

| Area | Coverage and interpretation |
| --- | --- |
| Client and workflow contracts | CLI, wizard and GUI interactions, inputs, planning, preferences, cancellation, updates and result records. Validate device-specific installation separately. |
| Resources and performance | WSL/Lima configuration, previews and backups, interprocess locks, effective limits, observed workers, optional timing and input/output integrity. Shared runners do not enforce large-BAM performance thresholds. Exit code 137 alone cannot establish OOM. |
| Presentation | Sample mapping, original names, HTML and TSV, canonical exports and PDF text. Manual usability tests cover rendering on the final device. |
| Windows | Prerequisites, staged embedded Python, bootstrap, layout, repair/removal, Inno fixture and signature inventory. |
| Ubuntu | APT dependencies, non-root analyses, reinstall/removal and, for the 0.9.10 installer, an upgrade from the published 0.9.9 DEB. |
| macOS | Native Intel and ARM64 packages, launchers, Lima transport and configuration. Runtime tests on actual VMs require the separate jobs described below. |
| Scientific engine | Five modules, composed workflows, synthetic BAMs, invalid inputs, numerical comparisons and original inputs preserved. Domain-researcher validation on real datasets is separate. |
| Documentation | Repository Markdown links, assets and anchors are checked offline. External site availability and scientific claims need separate review. |

## Scientific checks

The shorter DNP/SNP workflow uses the three BAMs in the [offline synthetic trio (ZIP)](../examples/newpat-synthetic-trio.zip). It goes through desktop plan preparation and the execution engine. For each caller it checks three loci per sample against the [versioned regression oracle](https://github.com/GregorioDalia/nipat-desktop/blob/caf6cf4c0c9473831a01250fc0f3f84d3e64cf0e/tests/fixtures/synthetic-trio-v1/README.md), including chromosome, coordinates, alleles, counts and genotype. The oracle records input digests and expected results independently of tables written by the candidate. This catches broken input handling while keeping the independent upstream comparisons available for scientific changes.

The same rapid check runs two small cases from the existing engine fixtures in the candidate image. DNP sample A has 20 ALT reads and one Other read at positions 230–231 and must return `1/1`. The two SNP sites have one Other read among seven and six total reads, respectively. Both must return the literal `NA` at the default 10% Other threshold. The check compares coordinates, alleles, counts and genotypes for all five additional rows against the versioned tables. The three-sample desktop demo still has its original 18 expected rows.

`scripts/verify_r_equivalence.py` compares 17 caller cases against frozen references, NIPAT 0.8.5 for DNP and SNPcall 2.0 for SNP, producing `r-equivalence.json`. The comparisons cover exact scientific tables and unrounded R results. Plot checks cover content, dimensions, histograms and rendering across serial and parallel modes of the candidate.

`scripts/verify_five_modules.py --image IMAGE --full` compares Contamination, prenatal CPI and postnatal CPI with the upstream NEWPAT snapshot `97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4` and independent analytical expectations. Its `five-module-qualification.json` covers 86 runs, including 16 upstream comparisons and 54 batch cases. Batches exercise 2/3/5 families or samples, both SNP/DNP marker types, and serial, automatic and two-worker execution. Upstream numerical tolerances are absolute and relative `1e-11`; sample, pair and trio identities must match exactly.

The routine caller check runs only the candidate on the bundled inputs. Independent analytical expectations for the downstream modules also exist in `tests/fixtures/five_modules` in the source checkout. The [validation guide](VALIDATION.md) lists the additional model checks. The seven-check scientific qualification and the current release acceptance schema still require the pinned upstream comparisons. For a change to a scientific model, record the input, expected result, units or scale, missing-value behavior, and the reason for the changed expectation alongside its test. Validate a new or corrected module against its author’s example before using that example as a regression reference. A future change to the release evidence contract needs explicit coverage of the current cases and a versioned verifier that can still read historical records.

The container supplies R, samtools, model scripts, adapters and orchestration. The client verifies contracts. Scientific scripts used for execution come from the image. The final-image checks exercise synthetic read mixtures, FASTA changes, analytical CPI and contamination expectations, and the current postnatal site contract in the existing native R job. Its JSON report records outcomes and test durations. [Suite and local replay](VALIDATION.md#repeat-the-scientific-correctness-suite) A three-BAM, ten-step plan exercises DNP, SNP and all three downstream modules for both callers, in serial and capped at two processes. It checks expected outputs, run identity, settings and original inputs. Presentation checks verify canonical tables with/without readable names and PDF text. The catalog pins distributed scientific sources and preparation dependencies by hash.

Both scientific reports are required and must identify the same immutable image. Upstream reference fixtures stay in tests. Linux AMD64 numerical results do not establish the behavior of the Lima/Rosetta transport on an Apple Silicon device.

## Installer construction

The manual build accepts a matching release revision of `main`, `release/VERSION` or `release/VERSION-…`. Package and client versions must match the reviewed source. The Windows checks and Linux runtime build can run in parallel after source verification. Windows package construction depends on the relevant Windows and runtime outputs. The default full build requires all four installers and their shared archive to pass `installer-required`.

For a local Windows test, select **Installers (review build)**, choose the reviewed revision and enable `windows_zip_only`. A Linux runner prepares the same scientific image and WSL filesystem used by the complete ZIP. A Windows runner builds and extracts the ZIP and checks the embedded client. Download `newpat-windows-review-zip` from that run. This mode skips the full scientific qualification, Windows setup EXE and macOS/Ubuntu installers. Official acceptance requires a separate full build.

| Artifact | Package or evidence |
| --- | --- |
| `nipat-windows-setup` | Windows bootstrap, release payload, complete local ZIP and reports |
| `nipat-linux-setup` | Ubuntu AMD64 DEB and reports |
| `nipat-macos-setup-arm64`, `nipat-macos-setup-x86_64` | macOS PKG and report for each native architecture |
| `nipat-installer-set-evidence` | Joint identity and verification report |
| `newpat-acceptance-template-<attempt>` | Pending acceptance record with build identity and digests for the full installer set |

The final job downloads the original packages to verify their identities, then publishes its evidence without uploading another four copies of the packages. Actions artifacts contain review material and have retention limits. Users of a published release download the installer from its Assets list.

<a id="riuso-delle-evidenze-scientifiche"></a>

## Scientific evidence reuse

After executing all seven scientific checks successfully, a trusted CI run uploads `nipat-scientific-qualification-N-TREE`, where N is the workflow attempt and TREE is the full Git tree. It contains a descriptor and bounded synthetic text evidence. The producer also saves the tested image by its immutable Docker ID in a separate Actions artifact retained for three days. The qualification binds the saved archive to the scientific results. This lets a consumer load the same image even when a fresh Docker build from the same sources would produce a different ID.

Reuse requires all of the following:

- An identical tracked tree and clean worktree, including code, workflows, verifiers, fixtures and dependency definitions.
- The same full Docker image ID, Linux OS and AMD64 architecture.
- Verifiable checkout provenance, including the actual PR merge revision when applicable; a fork's CI cannot supply this evidence.
- Successful run, scientific job and all seven checks in the same attempt.
- For 0.9.10, a completed, passing `native-r.json` with the required test suites, no skipped tests and digests matching the suite sources and scientific manifest of the build. Schema 2 also records the number of subcases executed. The verifier compares that count with the retained results and checks the report format against the runner at the build commit.
- Matching artifact identity, transport digest and every descriptor entry, including limits on paths, files and total size.

Distinct commits may have the same tree. A documentation change normally changes the tree and invalidates reuse. Identical Dockerfiles alone do not establish identical images. The build restores verified reports with their original timestamps, results and image identity. `build/scientific-reuse/reuse.json` records reuse or fresh execution, the consumer and the original producer where applicable.

On a push to protected `main`, CI looks up the pull request merged at that commit, then checks the producing run, its Git tree and host tools. A successful lookup writes a receipt pointing to the original producer. Only a run that executed the checks can issue a new qualification. If any requirement fails or the reports have expired, CI runs all seven checks.

The full installer build first searches up to 30 completed CI runs with a two-minute lookup budget. On a miss it can wait up to 15 minutes for an identified CI run already qualifying that source. If the candidate succeeds, the installer repeats the full evidence lookup. If the image or its evidence is missing, expired or fails verification, the job builds the image and runs the full scientific suite. Independent Windows checks can proceed while the Linux job waits. The build verifies the client, evidence preflight, WSL runtime, exported archive in the distributed engine and each installer on either path.

<a id="audit-windows-e-concorrenza-dalla-0820"></a>

## Windows and macOS qualification

The Windows job verifies reproducibility of the C# components involved. The Inno fixture exercises install, update and removal using substitutes for the bootstrap and desktop prerequisites in that fixture. Its evidence explicitly records `production_setup_executed: false`. The Authenticode report records signature states and verification failures. Smart App Control needs separate observation on the target Windows device. Scientific concurrency checks cover DNP 2-, 3- and 6-BAM differential cases and actual per-coordinator and global worker overlap relative to the budget.

For real Lima tests, enable `qualify_macos_runtime` on trusted self-hosted runners labeled `macOS`, `nipat-runtime` and `ARM64` or `X64`, with virtualization available. Record host architecture, hardware, macOS, Lima/Rosetta versions, commit and PKG hash. Treat architectures separately. Finder permissions and Gatekeeper interactions require their own device observations. Run trusted release code on these dedicated runners.

## Publication and reruns

Integrate the built source first. Merging an acceptance-only PR can trigger publication after Linux acceptance CI succeeds on `main`. The publisher checks the originating CI attempt, its successful acceptance and required jobs, and the full push interval recorded by CI. A normal code merge ends with CI. Automatic publication requires that the entire push changed only acceptance records, including when the merge adds several commits. The publisher verifies package and remote asset digests, permits recovery of a matching draft and serializes manual and automatic publishing. A mixed change or a deliberate two-stage release can use manual dispatch. Follow the [release procedure](../.github/RELEASE.md) for exact inputs, records, update feeds and draft verification.

The recorded `stable` channel publishes a numeric official release. GitHub **Latest** advances only when the accepted version is newer than the current default download. `testing` publishes a prerelease. CI artifacts and drafts do not enter the update feeds. Active installers distinguish Windows bootstrap, complete ZIP, Ubuntu and macOS feeds. The [validation record](VALIDATION.md) tracks domain observations independently.

For a transient failure on the same commit, review the job logs and rerun failed jobs. A changed source needs evidence for the new revision. When analyzing build time, distinguish queueing, execution and the dependency chain. Parallel job duration sums exceed elapsed time. The [historical build timing profile](https://github.com/GregorioDalia/nipat-desktop/blob/main/docs/archive/README.md#profilo-storico-della-build-degli-installatori) provides one recorded example.

## Preparing the GitHub repository rename

The published 0.9.9 downloads use `GregorioDalia/nipat-desktop`. The planned name is `GregorioDalia/NewPat-Desktop`. Both identify the same GitHub repository after a rename. Its numeric ID is `1307623649`. The desktop product ID, APT package identity, WSL/Lima ownership, installation directories, image tags and existing release checksums are independent of this name.

Before renaming, distribute a version that recognizes both names. GitHub returns the current repository name in release metadata, including metadata for previously published releases. The 0.9.9 updater compares release and asset URLs against the old name exactly. Its automatic discovery can fail as soon as GitHub starts returning the new name, even if a browser follows the old download links. For the Windows complete ZIP and retained bootstrap, use a fresh 0.9.10 installer or complete ZIP for the English launcher transition. Keep every published 0.9.9 asset and manifest byte-for-byte intact.

1. Merge and test the transition on the existing repository. Verify publication guards against the numeric repository ID, the two allowed names, the required branch/event and source provenance. Publish the intended transition build under the existing name and check the installer and update paths on the supported platforms.
2. When the maintainer chooses the cutover, change the existing repository name in **Settings → General**. Keep the old repository name unused. GitHub redirects ordinary repository and Git traffic. Project-site URLs and invocations of a hosted Action by its old name have separate behavior. Check external integrations, bookmarks, badges, Pages and invocations outside this repository as applicable. [GitHub's rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)
3. After the rename, verify the identity and update each existing checkout where `origin` points to the official repository. These read-only checks and local remote update work in PowerShell or a POSIX shell.

   ```sh
   gh api repos/GregorioDalia/NewPat-Desktop --jq '[.id, .full_name]'
   git remote set-url origin https://github.com/GregorioDalia/NewPat-Desktop.git
   git ls-remote origin refs/heads/main refs/tags/v0.9.9
   ```

4. Confirm the API reports `1307623649` and `GregorioDalia/NewPat-Desktop`. Check the 0.9.9 tag, old release links, canonical provider URLs, downloads and recorded checksums. Test a fresh install, a transition-version update check, and a local update from each active packaging channel. Run CI and the installer build under the renamed repository before the next publication. Update active public download links and the default repository hint to the new address once it resolves. Historical evidence retains its original links.
