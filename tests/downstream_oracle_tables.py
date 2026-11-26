"""Write small, deterministic SNP/DNP tables used by the downstream model oracles."""

import csv


def coordinate_header(marker):
    return ("chr", "pos") if marker == "SNP" else ("chr", "pos1", "pos2")


def coordinate(marker, locus):
    start = 10 * locus
    chromosome = "NA" if locus % 3 == 0 else "01"
    return (chromosome, start) if marker == "SNP" else (chromosome, start, start + 1)


def alleles(marker):
    return ("A", "T") if marker == "SNP" else ("AG", "TC")


def write_table(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)


def write_calls(path, marker, counts, *, swap=False):
    bases = alleles(marker)
    rows = []
    for locus, (ref, alt, other) in counts:
        pair = bases[::-1] if swap else bases
        reads = (alt, ref, other) if swap else (ref, alt, other)
        total = sum(reads)
        rows.append((*coordinate(marker, locus), *pair, *reads, total if total else "NA"))
    write_table(path, (*coordinate_header(marker), "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count"), rows)
