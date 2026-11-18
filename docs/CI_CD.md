# Continuous integration and release builds

The repository separates source verification, installer construction and publication. A green source CI run identifies the checks that passed for that revision. Release acceptance and verification bind the distributed packages to their source and scientific image.

| Workflow | Trigger | Result |
| --- | --- | --- |
| [CI](../.github/workflows/ci.yml) | Pull request, push to `main`, or manual dispatch | Required checks for the changed files, with dedicated Linux jobs for documentation and release acceptance |
| [Installers (review build)](../.github/workflows/windows-installer.yml) | Manual dispatch on a reviewed release revision | Windows, Ubuntu and both macOS packages, Windows ZIP/payload, manifests and package evidence |
| [Prepare or publish verified release](../.github/workflows/publish-windows-release.yml) | Manual dispatch on `main` | Verified draft, publication of a verified draft, or combined preparation and publication |
| [Publish accepted release](https://github.com/GregorioDalia/nipat-desktop/blob/main/.github/workflows/publish-accepted-release.yml) | Successful qualifying CI push on `main` | Selection of acceptance-only changes and publication of the identified accepted build |
| [Published runtime security report](../.github/workflows/security-monitoring.yml) | Scheduled or manual dispatch | Inventory and findings for published images |

## Source verification

CI uses the Git change set to select relevant tests and `required` to check their outcomes. Development branches normally receive CI via pull requests. A branch without an open PR can use manual dispatch. Full installer builds run separately on request.

When a change consists entirely of recognized guides, CI runs the `documentation` job on Linux. It checks repository links and heading anchors, parses CLI examples in the current user guides, validates the documented workflow plan and compares shipping text with the contents of small archives created by the Windows package builders. Changes to `LICENSE` or `THIRD_PARTY_NOTICES.md` trigger scientific qualification. CI also checks both files inside the built image against their source hashes. A manual CI dispatch selects all integration layers.

An unavailable comparison or an unfamiliar workflow change receives conservative coverage. Changes to core CI, its selector or installer construction retain applicable integration levels. Changes limited to the manual publisher activate its fast and packaging checks. Changes to automatic publication select the complete integration matrix. A simultaneous scientific change requires scientific checks.

A change limited to `.github/release-acceptance/vVERSION.json` uses `acceptance` and `required` on Linux. The job fetches bounded textual evidence to verify the build, source, completed platform jobs, four package digests, common manifest, historical baseline and scientific reports. A mixed change checks the affected acceptance records alongside the applicable source checks. Missing or mismatched records fail verification.

| Area | Coverage and interpretation |
| --- | --- |
| Client and workflow contracts | CLI, wizard and GUI interactions, inputs, planning, preferences, cancellation, updates and result records. Validate device-specific installation separately. |
| Resources and performance | WSL/Lima configuration, previews and backups, interprocess locks, effective limits, observed workers, optional timing and input/output integrity. Shared runners do not enforce large-BAM performance thresholds. Exit code 137 alone cannot establish OOM. |
| Presentation | Sample mapping, original names, HTML and TSV, canonical exports and PDF text. Manual usability tests cover rendering on the final device. |
| Windows | Prerequisites, staged embedded Python, bootstrap, layout, repair/removal, Inno fixture and signature inventory. |
| Ubuntu | APT dependencies, non-root analyses, reinstall/removal and update from the recorded 0.7.2 package. |
| macOS | Native Intel and ARM64 packages, launchers, Lima transport and configuration. Runtime tests on actual VMs require the separate jobs described below. |
| Scientific engine | Five modules, composed workflows, synthetic BAMs, invalid inputs, numerical comparisons and original inputs preserved. Domain-researcher validation on real datasets is separate. |
| Documentation | Repository Markdown links, assets and anchors are checked offline. External site availability and scientific claims need separate review. |

## Scientific checks

`scripts/verify_r_equivalence.py` compares 17 caller cases against frozen references, NIPAT 0.8.5 for DNP and SNPcall 2.0 for SNP, producing `r-equivalence.json`. The comparisons cover exact scientific tables and unrounded R results. Plot checks cover content, dimensions, histograms and rendering across serial and parallel modes of the candidate.

`scripts/verify_five_modules.py --image IMAGE --full` compares Contamination, prenatal CPI and postnatal CPIN with upstream NEWPAT commit `9c2a8be60afcb944153710da6a61cd0559e2b4cf` and independent analytical expectations. Its `five-module-qualification.json` covers 86 runs, including 16 upstream comparisons and 54 batch cases. Batches exercise 2/3/5 families or samples, both SNP/DNP marker types, and serial, automatic and two-worker execution. Upstream numerical tolerances are absolute and relative `1e-11`; sample, pair and trio identities must match exactly.

The container supplies R, samtools, model scripts, adapters and orchestration. The client verifies contracts. Scientific scripts used for execution come from the image. The final-image checks run native empty/zero-coverage and parameter cases with required dependencies. A three-BAM, ten-step plan exercises DNP, SNP and all three downstream modules for both callers, in serial and capped at two processes. It checks expected outputs, run identity, settings and original inputs. Presentation checks verify canonical tables with/without readable names and PDF text. The catalog pins distributed scientific sources and preparation dependencies by hash.

Both scientific reports are required and must identify the same immutable image. Upstream reference fixtures stay in tests. Linux AMD64 numerical results do not establish the behavior of the Lima/Rosetta transport on an Apple Silicon device.

## Installer construction

The manual build accepts a matching release revision of `main`, `release/VERSION` or `release/VERSION-…`. Package and client versions must match the reviewed source. The Windows checks and Linux runtime build can run in parallel after source verification. Windows package construction depends on the relevant Windows and runtime outputs. The aggregate `installer-required` job checks all four installers and their shared archive. A failed required platform blocks publication.

| Artifact | Package or evidence |
| --- | --- |
| `nipat-windows-setup` | Windows bootstrap, release payload, complete local ZIP and reports |
| `nipat-linux-setup` | Ubuntu AMD64 DEB and reports |
| `nipat-macos-setup-arm64`, `nipat-macos-setup-x86_64` | macOS PKG and report for each native architecture |
| `nipat-installer-set-evidence` | Joint identity and verification report |

The final job downloads the original packages to verify their identities, then publishes its evidence without uploading another four copies of the packages. Actions artifacts contain review material and have retention limits. Users of a published release download the installer from its Assets list.

<a id="riuso-delle-evidenze-scientifiche"></a>

## Scientific evidence reuse

After executing all seven scientific checks successfully, a trusted CI run uploads `nipat-scientific-qualification-N-TREE`, where N is the workflow attempt and TREE is the full Git tree. It contains a descriptor and bounded synthetic text evidence. Consumers build the image and inspect its identity before looking up a qualification.

Reuse requires all of the following:

- An identical tracked tree and clean worktree, including code, workflows, verifiers, fixtures and dependency definitions.
- The same full Docker image ID, Linux OS and AMD64 architecture.
- Verifiable checkout provenance, including the actual PR merge revision when applicable; a fork's CI cannot supply this evidence.
- Successful run, scientific job and all seven checks in the same attempt.
- Matching artifact identity, transport digest and every descriptor entry, including limits on paths, files and total size.

Distinct commits may have the same tree. A documentation change normally changes the tree and invalidates reuse. Identical Dockerfiles alone do not establish identical images. The build restores verified reports with their original timestamps, results and image identity. `build/scientific-reuse/reuse.json` records reuse or fresh execution, the build and the original producer where applicable.

On a push to protected `main`, CI also verifies that the producing pull request actually merged at the push commit and that the recorded host tools match. A successful lookup writes a receipt pointing to the original producer. Only a run that executed the checks can issue a new qualification. If any requirement fails or the reports have expired, CI runs all seven checks.

The installer first searches up to 30 completed CI runs with a two-minute lookup budget. On a miss it can wait up to 15 minutes for an identified CI run already qualifying that source. If the candidate succeeds, the installer repeats the full evidence lookup. Otherwise it runs the scientific suite itself. Independent Windows checks can proceed while the Linux job waits. The build verifies the client, evidence preflight, WSL runtime, exported archive in the distributed engine and each installer on either path.

<a id="audit-windows-e-concorrenza-dalla-0820"></a>

## Windows and macOS qualification

The Windows job verifies reproducibility of the C# components involved. The Inno fixture exercises install, update and removal using substitutes for the bootstrap and desktop prerequisites in that fixture. Its evidence explicitly records `production_setup_executed: false`. The Authenticode report records signature states and verification failures. Smart App Control needs separate observation on the target Windows device. Scientific concurrency checks cover DNP 2-, 3- and 6-BAM differential cases and actual per-coordinator and global worker overlap relative to the budget.

For real Lima tests, enable `qualify_macos_runtime` on trusted self-hosted runners labeled `macOS`, `nipat-runtime` and `ARM64` or `X64`, with virtualization available. Record host architecture, hardware, macOS, Lima/Rosetta versions, commit and PKG hash. Treat architectures separately. Finder permissions and Gatekeeper interactions require their own device observations. Run trusted release code on these dedicated runners.

## Publication and reruns

Integrate the built source first. Merging an acceptance-only PR can trigger publication after Linux acceptance CI succeeds on `main`. The selector verifies the originating repository, push, commit and successful jobs. The publisher verifies package and remote asset digests, permits recovery of a matching draft and serializes manual and automatic publishing. A mixed change or a deliberate two-stage release can use manual dispatch. Follow the [release procedure](../.github/RELEASE.md) for exact inputs, records, update feeds and draft verification.

The recorded `stable` channel publishes a numeric official release as **Latest**. `testing` publishes a prerelease. CI artifacts and drafts do not enter the update feeds. Active installers distinguish Windows bootstrap, complete ZIP, Ubuntu and macOS feeds. The [validation record](VALIDAZIONE.md) tracks domain observations independently.

For a transient failure on the same commit, review the job logs and rerun failed jobs. A changed source needs evidence for the new revision. When analyzing build time, distinguish queueing, execution and the dependency chain. Parallel job duration sums exceed elapsed time. The [historical build timing profile](https://github.com/GregorioDalia/nipat-desktop/blob/main/docs/archive/README.md#profilo-storico-della-build-degli-installatori) provides one recorded example.
