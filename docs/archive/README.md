# Documentation archive

These records refer to identified releases, revisions and tests. Files retain their original paths so that older citations continue to work. For installing and using NewPat, see the [current guides](../README.md).

## Release notes

| Series | Records |
| --- | --- |
| 0.9 | [0.9.7](../RELEASE_0.9.7.md) · [0.9.5](../RELEASE_0.9.5.md) · [0.9.1](../RELEASE_0.9.1.md) · [0.9.0](../RELEASE_0.9.0.md) |
| 0.8 | [0.8.99](../RELEASE_0.8.99.md) · [0.8.95](../RELEASE_0.8.95.md) · [0.8.90](../RELEASE_0.8.90.md) · [0.8.81](../RELEASE_0.8.81.md) · [0.8.80](../RELEASE_0.8.80.md) · [0.8.70](../RELEASE_0.8.70.md) · [0.8.60](../RELEASE_0.8.60.md) · [0.8.50](../RELEASE_0.8.50.md) · [0.8.35](../RELEASE_0.8.35.md) · [0.8.30](../RELEASE_0.8.30.md) · [0.8.20](../RELEASE_0.8.20.md) · [0.8.14](../RELEASE_0.8.14.md) · [0.8.9](../RELEASE_0.8.9.md) · [0.8.5](../RELEASE_0.8.5.md) · [0.8.2](../RELEASE_0.8.2.md) · [0.8.0a1](../RELEASE_0.8.0a1.md) |
| 0.7 and 0.6 | [0.7.2](../RELEASE_0.7.2.md) · [0.7.1](../RELEASE_0.7.1.md) · [0.7.0a1](../RELEASE_0.7.0a1.md) · [0.6.0](../RELEASE_0.6.0.md) |
| 0.5, 0.4 and 0.3 | [0.5.0a1](../RELEASE_0.5.0a1.md) · [0.4.1](../RELEASE_0.4.1.md) · [0.4.0](../RELEASE_0.4.0.md) · [0.3.0a2](../RELEASE_0.3.0a2.md) · [0.3.0a1](../RELEASE_0.3.0a1.md) |

## Audits, tests and decisions

- Technical audits for [0.8.80](../AUDIT_0.8.80.md), [0.8.70](../AUDIT_0.8.70.md), [0.8.60](../AUDIT_0.8.60.md), [0.8.50](../AUDIT_0.8.50.md) and [0.8.20](../AUDIT_0.8.20.md).
- [0.8.50 development](../DEVELOPMENT_0.8.50.md) and [0.8.50 installed-package acceptance](../COLLAUDO_INSTALLAZIONE_0850.md).
- Performance studies for [0.8.14](../OPTIMIZATIONS_0.8.14.md), [0.8.13 pileups](../PILEUP_0.8.13.md), [0.8.12 parallel execution](../PARALLELISMO_0.8.12.md), the [0.8.10 prototype](../PROTOTYPE_0.8.10.md) and [0.8.9 optimizations](../OPTIMIZATION_0.8.9.md).
- Machine-readable evidence for [0.8.50](../validation/0.8.50-development.json), [0.8.14 microbenchmarks](../validation/0.8.14-microbenchmarks.json), [observed 0.8.14 benchmarks](../validation/0.8.14-observed-benchmarks.json), and rootless testing of [0.8.14](../validation/0.8.14-rootless.json), [0.8.13](../validation/0.8.13-rootless.json) and [0.8.12](../validation/0.8.12-rootless.json).
- [Acceptance records and reports](../../.github/release-acceptance), [early decisions](DECISIONS.md) and the [0.5 development plan](PIANO_0.5.md).

## Timing of a historical installer build

[Build 43430275209](https://github.com/GregorioDalia/nipat-desktop/actions/runs/43430275209) on 13 November 2026 illustrates the difference between one build's critical path and the cumulative time spent on retries.

| Critical-path stage | Duration |
| --- | ---: |
| Identify source | 21 s |
| Windows checks | 3 min 34 s |
| Linux runtime, regressions and export | 19 min 54 s |
| Four installers, built in parallel | 5 min 48 s |
| Collect artifacts and run the final check | 2 min 32 s |
| Job startup and intervals | 16 s |
| **Total** | **32 min 25 s** |

Scientific checks accounted for 13 min 55 s of the Linux job, Python tests for 53 s and release checks for 3 s. The last evidence-file limit check failed after all four installers had finished. Seven candidate build attempts before the final fix took 75 min 45 s cumulatively. Parallel CI execution time does not add to the operator's wait.

The subsequent evidence preflight uses the same reader and limits as final archive verification, before export and packaging. The final installer check is still required. On evidence from the failed attempt, preflight read 3,602 files in 1.34 s and would have detected the old limit about 12 minutes earlier. It makes little difference to the elapsed time of an already successful build.
