# Scientific code review for 0.8.9

This release revised the four R programs to reduce allocations and repeated work and clarified resource configuration. The [release notes](RELEASE_0.8.9.md) describe distribution and verification. This record defines the reference and comparison criteria.

## Reference

The baseline is `v0.8.5`, commit `eafadf7002a9c7d7c1b9af9ccafc47d698a059e5`, including its released compatibility changes. Immutable copies of six R files and their SHA-256 manifest are in [the test reference directory](../tests/reference_r/0.8.5/README.md). Only tests use these copies. The installer uses the candidate in the engine's normal directories.

## Changes

| Component | Revision |
| --- | --- |
| DNPcall | Build observations directly, look up quality conversions, reuse extraction from repeated strings, group once, index by locus and remove duplicate counting. |
| SNPcall | Read the required columns, build observations directly and aggregate necessary features per read, preserving global QNAME grouping. |
| CPI | Compute once per pair/panel, select only the PI values, share work across equivalent thresholds, preallocate columns and reuse samples shared by consecutive pairs. |
| Contamination | Collect summary rows and assemble them once at the end. |
| Resource configuration | Distinguish saved settings, effective resources, suggestions and new limits. Pressing Enter retains the current value. |

The equivalence contract covers formulas, thresholds, samtools BAM access and scientific output formats. This revision introduced no new language or R dependency. Indexed access policy, block processing, plot dimensions and remaining-time estimates require separate verification.

For regular pileups, DNPcall and SNPcall split bases, names and qualities directly, without constructing strings with artificial separators. Missing values, spaces or unequal lengths select the compatible preparation path. SNPcall preserves associations between reads in different windows. DNPcall assigns shared observations to all applicable overlapping loci.

CPI computes statistics once for thresholds selecting the same loci, then restores every original row. Means, medians and plots retain the weight of each threshold. CPI multiplies indices in the original order without substituting cumulative products or log sums. Reuse covers the current and next pair, bounding the retained input set.

## Equivalence checks

| Output | Criterion |
| --- | --- |
| Scientific tables | Identical files, headers, order, values and missing-value representation. No general numerical tolerance. |
| Test-visible intermediates | Equal unrounded quantities and per-threshold series for the covered cases. |
| PDF | Same documents and rendered pages. Nondeterministic metadata such as creation date may differ. |
| Logs | Retained for diagnosis. Timings, temporary paths and grouping messages are operational metadata. |

The reference and candidate execute in the same environment with runtime and source identities recorded. Fixtures cover ordinary cases and boundaries of formulas and grouping. Passing demonstrates agreement on those cases. External-data benchmarks are separate.

## Running the comparisons

From the checkout root, with Docker Engine available, build the candidate and run the verifier in a fresh output directory:

```sh
docker build -f docker/scientific-runtime/Dockerfile -t nipat-scientific-runtime:r089 .
python scripts/verify_r_equivalence.py --image nipat-scientific-runtime:r089 --output-dir build/r-equivalence-089
```

PDF comparison uses Poppler's `pdftoppm` on the verification host. Read `r-equivalence.json` and logs to distinguish runtime failures, changed references and differing results. CI and the installer build use the same check and propagate failures.

## Performance and distribution

Check numerical equivalence before evaluating speed or memory. Use the same inputs, parameters, assigned resources and diagnostics for both versions. Record commit, image, outputs, timings and memory peaks. Fixture times do not predict large-BAM performance or impose timing thresholds on shared runners.

Publication binds revised R sources, equivalence reports, scientific image, build and installers using commit identities and checksums. The 0.8.9 acceptance applies only to its artifacts. Review builds and comparisons alone do not alter the stable channel. See [CI/CD](CI_CD.md). Subsequent work was collected in a single 0.8.10 prototype with identifiable commits and extended comparisons. At that point 0.8.9 remained official until a later stable release was approved.
