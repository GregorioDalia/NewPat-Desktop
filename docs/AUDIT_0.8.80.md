# Desktop preparation audit for 0.8.80

The review covered the five analysis modules, compound workflows, text wizard and CLI, the remaining items from the [0.8.70 audit](AUDIT_0.8.70.md), and the checks integrated in [PR 46](https://github.com/GregorioDalia/nipat-desktop/pull/46).

## Changes and checks

| Area | Change | Verification |
| --- | --- | --- |
| Contig identity and BAM input | SNP preserves textual contigs. The callers check contig names and lengths and the compatibility of BAM dictionaries, reference and markers. | `01`, `1`, `NA`, missing contigs, incompatible dictionaries and ordinary samtools/R cases. |
| DNP summaries | Aggregate genotypes must agree with every individual table. | Altered summaries, missing samples or loci, and valid outputs. |
| D7, D8: plan and status | Form, summary and compiler agree on active branches and sample roles. Readers share the final record after input checks. | Asymmetric imports, inactive branches, family roles, large records and failed final checks. |
| D6: preferences | Coordinate writes across processes, merge independent fields and report conflicting changes. | Two sessions editing distinct fields or the same field. |
| D10: CLI outcomes | Return code 2 for an incomplete requested restart/verification or stop with incomplete cleanup. | Deferred and failed restarts, unconfirmed allocation, a stopped but unremoved container and full success. |
| D4: preparation | Stream check logs, use distinct timeouts for diagnostics and self-tests, and record resumable failures. | A hung check, output before exit, selective termination and resumption. Scientific runs and the wizard keep their own execution behavior. |
| D5: Ubuntu updates | Acknowledge helper startup separately from hashing the package, and verify the full package before APT. | Slow reads, modified package, cancellation during verification and terminal startup failure. |
| D9: help | Describe full workflows and derive the displayed update channel from the release and preferences. | Stable and prerelease versions with Stable/Testing preferences, without starting an update or an analysis. |

The build and CI run the relevant checks. Publication reports and `desktop-acceptance.json` identify the commit, packages and completed verification.

## Limits of the evidence

Windows testing and real-data timings in the 0.8.70 audit remain attributed to the versions actually tested. A comparison of the installed 0.8.80 on those inputs requires the input identities, settings, reference tables, phase timings and memory observations specified in the [performance protocol](PERFORMANCE.md). Successful execution alone does not establish numerical agreement.

The [pre-1.0 acceptance criteria](ACCETTAZIONE_INSTALLATORI.md) identify unexecuted desktop scenarios, including physical macOS VM tests when absent. Domain validation retains a separate record. Further optimization of DNP blocks and startup requires targeted measurements. The tested input, parameter, output and workflow-state contracts provide the basis for the graphical interface.
