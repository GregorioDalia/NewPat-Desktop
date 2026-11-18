# NewPat 0.9.9

## DNP and SNP execution

Joint DNP pileup can use up to five samtools processes on different target chromosomes. Each process uses all the selected BAMs in their original order. A larger sample set increases the estimated memory cost per process. The R calculation continues to divide eligible blocks across its own workers after pileup acquisition finishes.

SNPcall can split acquisition for an indexed, coordinate-sorted BAM across target chromosomes. It merges the parts in BAM header order before passing the pileup to R. The R caller can distribute genotype likelihoods for independent loci when a sample has enough work. Workflows with several SNP samples can also process independent samples concurrently when the memory estimate fits the configured budget.

Contamination can process independent input tables concurrently. Prenatal and postnatal CPI continue to process independent pairs and trios. The execution settings apply across these operations. Choose serial mode for a reference run or set a worker ceiling when sharing the machine. [Resource settings](RISORSE.md) · [Measuring performance](PERFORMANCE.md)

## Verification

A Linux development test used two indexed synthetic BAMs with 180,000 alignments each across six chromosomes. With the planner configured for 32 CPUs and 15,858 MiB, five samtools 1.21 processes overlapped. The 4,320-line pileup was byte-identical across the parallel run, the serial run and a single unpartitioned mpileup. This checks concurrency and equivalence on the fixture. Elapsed time on a Windows installation depends on its BAMs, storage and WSL allocation.

## Downloads

Choose the setup or complete ZIP for Windows x64, the matching Apple Silicon or Intel package for macOS, or the Debian package for Ubuntu x86_64. [Downloads](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.9)
