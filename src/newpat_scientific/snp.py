"""Prepare SNPcall inputs inside the scientific image without desktop imports."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import unicodedata

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newpat_scientific import dnp_pileup as pileup_pool

from newpat_scientific.errors import ValidationError
from newpat_scientific.presentation import validate_request_presentation
from newpat_scientific.files import require_file, require_sidecar, require_snp_pileup, write_input_report
from newpat_scientific.panels import (
    read_bam_dictionary, read_snp_list, reference_lengths, require_bam_targets, require_reference_windows,
    write_snp_bed, write_snp_list,
)
from newpat_scientific.settings import defaults, normalize_settings, samtools_options, settings_from_environment


REQUEST_FIELDS = {
    "schema_version", "workflow", "mode", "panel", "bam", "pileup", "reference",
    "work_dir", "out_dir",
}


@dataclass(frozen=True)
class SnpPreparation:
    preparation_command: list[str] | None
    native_arguments: list[str]
    generated_pileup: Path | None
    bam: Path | None
    target_lengths: dict[str, int]
    reference_lengths: dict[str, int]

    def _bam_header(self, run_command, work_dir):
        if self.bam is None:
            return 0, {}, False
        with TemporaryDirectory(prefix=".bam-header-", dir=work_dir) as directory:
            header = Path(directory) / "header.sam"
            code = run_command(["samtools", "view", "--no-PG", "-H", "-o", str(header), str(self.bam)])
            if code:
                return code, {}, False
            sequences, sorted_header = read_bam_dictionary(header, self.bam)
            require_bam_targets(self.bam, sequences, self.target_lengths, self.reference_lengths)
        return 0, sequences, sorted_header

    def validate_bam(self, run_command: Callable[[list[str]], int], work_dir: Path) -> int:
        return self._bam_header(run_command, work_dir)[0]

    def plan_acquisition(self, run_command: Callable[[list[str]], int], work_dir: Path
                         ) -> tuple[int, list[str] | None]:
        """Check the header once and retain the BAM target order for indexed mpileup."""
        code, sequences, sorted_header = self._bam_header(run_command, work_dir)
        if code or self.bam is None:
            return code, None
        contigs = [name for name in sequences if name in self.target_lengths]
        indices = [p for ext in (".bai", ".csi") for p in (Path(str(self.bam) + ext), self.bam.with_suffix(ext))
                   if p.is_file()]
        reason = None
        if os.getenv("NIPAT_EXECUTION_MODE") == "serial":
            reason = "requested-serial"
        elif os.getenv("NIPAT_PARALLEL_CHILD") == "1" or os.getenv("NIPAT_MAX_WORKERS") == "1":
            reason = "shared-worker-limit"
        elif not sorted_header or len(contigs) < 2:
            reason = "non-coordinate-header" if not sorted_header else "single-chromosome"
        elif not indices or any(p.stat().st_mtime_ns < self.bam.stat().st_mtime_ns for p in indices):
            reason = "missing-or-older-index"
        elif any(name == "." or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in contigs):
            reason = "ambiguous-contig"
        metadata = work_dir / "snp-acquisition.json"
        plan = {"strategy": "sequential-scan" if reason else "planning", "contigs": contigs,
                "largest_target_length": max(self.target_lengths.values()),
                "parallel": {"reason": reason or "planning", "workers": 1,
                             "observed_max_processes": None, "measurement": "direct-command-unmeasured"
                             if reason else "awaiting-supervisor"}, "processes": []}
        pileup_pool._write_json(metadata, plan)
        if reason:
            return 0, self.preparation_command
        return 0, [sys.executable, str(Path(__file__).resolve()), str(metadata), *self.preparation_command[2:]]


# Use the same R function as the other engine phases for cgroups, affinity,
# explicit limits, nested workers and the fixed desktop capacity document.
_R_BUDGET = """
a <- commandArgs(trailingOnly=TRUE)
source(a[[1]])
p <- nipat_parallel_budget(as.integer(a[[2]]), memory_mib=as.numeric(a[[3]]))
cat(jsonlite::toJSON(p, auto_unbox=TRUE, null="null"))
"""


class _PoolMemoryLimit(RuntimeError):
    pass


def _check_pool_rss(processes, limit_mib):
    """Yield to the original scan if live samtools exceed the pool's allowance."""
    rss_kib = 0
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            status = Path(f"/proc/{process.pid}/status").read_text()
        except FileNotFoundError:
            continue  # The process may finish between poll() and read_text().
        match = re.search(r"^VmRSS:\s+(\d+) kB$", status, re.MULTILINE)
        if match:
            rss_kib += int(match[1])
    if rss_kib > 1024 * limit_mib:
        raise _PoolMemoryLimit("samtools pool exceeded its memory allowance")


def _run_acquisition(metadata, arguments):
    document = json.loads(metadata.read_text())
    contigs = document["contigs"]
    if arguments[-3] != "-o":
        raise ValidationError("Output mpileup non valido.")
    output = Path(arguments[-2])
    command = ["samtools", "mpileup", *arguments[:-3], arguments[-1]]
    cancellation = pileup_pool.Cancellation()
    with pileup_pool.cancellation_handlers(cancellation), TemporaryDirectory(
            prefix=".snp-acquisition-", dir=output.parent) as tmp:
        staging = Path(tmp)
        budget_path = staging / "budget.json"
        # Allow for reference expansion and scratch/reader buffers per samtools.
        # Depth is deliberately unchanged. The live pool also has an RSS guard
        # because deep coverage and variable read lengths exceed static estimates.
        estimate = max(256, 2 * (64 + (document["largest_target_length"] + 1048575) // 1048576))
        staged_output = staging / "pileup.txt"
        try:
            with budget_path.open("xb") as handle:
                pileup_pool._execute(["Rscript", "--vanilla", "-e", _R_BUDGET,
                                      str(Path(__file__).with_name("parallel.R")), str(len(contigs)),
                                      str(estimate)], handle, cancellation)
            budget = json.loads(budget_path.read_text())
            plan = pileup_pool._budget(budget)
            available = max(0, (budget.get("memory_budget_mib") or 0) - (budget.get("coordinator_rss_mib") or 0)) / 2
            plan["workers"] = min(plan["workers"], max(1, int(available // estimate)))
            plan.update(tasks=len(contigs), pool_rss_limit_mib=available, measurement="supervised-samtools")
            document["parallel"] = plan
            completed = False
            if plan["workers"] > 1:
                document["strategy"] = plan["reason"] = "indexed-chromosomes"
                try:
                    with staged_output.open("xb") as handle:
                        pileup_pool._parallel_chromosomes(
                            contigs, command[:-1], staging, handle, cancellation, document, metadata,
                            monitor=lambda live: _check_pool_rss(live, available), inputs=[command[-1]],
                        )
                    completed = True
                except (_PoolMemoryLimit, pileup_pool.PileupError) as exc:
                    cancellation.check()
                    plan["reason"] = str(exc)
                    print(f"SNP acquisition: retrying the sequential scan ({exc})", file=sys.stderr)
            else:
                plan["reason"] = "single-worker-budget"
            if not completed:
                document["strategy"] = "sequential-scan"
                with staged_output.open("wb") as handle:
                    pileup_pool._tracked_execute(command, handle, cancellation, document,
                                                {"stage": "mpileup-sequential"})
            cancellation.check()
            os.replace(staged_output, output)
            document["status"] = "completed"
        except BaseException:
            document["status"] = "cancelled" if cancellation.signum else "failed"
            raise
        finally:
            pileup_pool._write_json(metadata, document)


def _absolute_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or any(
        unicodedata.category(char) == "Cc" for char in value
    ):
        raise ValidationError(f"{label}: percorso non valido.")
    path = Path(value)
    if not path.is_absolute():
        raise ValidationError(f"{label}: occorre un percorso assoluto nel container.")
    return path.resolve()


def prepare_snp(request: object) -> SnpPreparation:
    """Validate a request before writes and describe samtools/R execution.

    SNPcall 2.0 uses three-base windows and base qualities, with uncapped depth by default.
    Indexes are supplied as read-only sidecars, never generated next
    to user inputs. Only BAM mode writes the BED and later produces a pileup.
    """
    if (not isinstance(request, dict) or not REQUEST_FIELDS <= set(request)
            or set(request) - REQUEST_FIELDS - {"presentation", "scientific_settings"}):
        raise ValidationError("Richiesta SNPcall non valida: campi mancanti o inattesi.")
    validate_request_presentation(request)
    scientific = (normalize_settings("snp-call", request["scientific_settings"])
                  if "scientific_settings" in request else settings_from_environment("snp-call"))
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValidationError("Versione della richiesta SNPcall non supportata.")
    if request["workflow"] != "snp-call":
        raise ValidationError("Workflow della richiesta SNPcall non valido.")
    mode = request["mode"]
    if not isinstance(mode, str) or mode not in {"bam", "pileup"}:
        raise ValidationError("Modalità SNPcall non valida: scegliere bam oppure pileup.")
    if mode == "bam":
        if request["bam"] is None or request["reference"] is None or request["pileup"] is not None:
            raise ValidationError("La modalità BAM richiede BAM e riferimento, senza pileup.")
    elif request["pileup"] is None or request["bam"] is not None or request["reference"] is not None:
        raise ValidationError("La modalità pileup richiede soltanto il pileup, senza BAM o riferimento.")

    panel = require_file(_absolute_path(request["panel"], "Lista SNP"), "Lista SNP")
    panel_rows = read_snp_list(panel, for_bed=mode == "bam")
    positions = [(row.chromosome, row.position) for row in panel_rows]
    sources = [panel]
    bam = reference = None
    target_lengths = {}
    lengths = {}
    if mode == "bam":
        bam = require_file(_absolute_path(request["bam"], "BAM"), "BAM")
        reference = require_file(_absolute_path(request["reference"], "FASTA"), "FASTA")
        fasta_index = require_sidecar(reference, ".fai", "Indice FASTA").resolve()
        sources.extend([bam, reference, fasta_index])
        if reference.suffix.lower() in {".gz", ".bgz", ".bgzf"}:
            sources.append(require_sidecar(reference, ".gzi", "Indice FASTA BGZF").resolve())
        lengths = reference_lengths(fasta_index)
        target_lengths = require_reference_windows(lengths, (
            (chromosome, position - 1, position + 1) for chromosome, position in positions
        ))
        for suffix in (".bai", ".csi"):
            for candidate in (Path(str(bam) + suffix), bam.with_suffix(suffix)):
                if candidate.is_file():
                    sources.append(candidate.resolve())
    else:
        pileup = require_file(_absolute_path(request["pileup"], "Pileup SNP"), "Pileup SNP")
        require_snp_pileup(pileup)
        sources.append(pileup)

    work_dir = _absolute_path(request["work_dir"], "Cartella di lavoro")
    out_dir = _absolute_path(request["out_dir"], "Cartella risultati")
    if work_dir.is_relative_to(out_dir) or out_dir.is_relative_to(work_dir):
        raise ValidationError("Le cartelle di lavoro e risultati devono essere distinte e non sovrapposte.")
    for source in sources:
        if source.is_relative_to(work_dir) or source.is_relative_to(out_dir):
            raise ValidationError("Gli input non possono trovarsi nelle cartelle di lavoro o risultati.")
    for directory in (work_dir, out_dir):
        if directory.exists() and not directory.is_dir():
            raise ValidationError(f"La destinazione non è una cartella: {directory}")
    if out_dir.is_dir() and any(out_dir.iterdir()):
        raise ValidationError("La cartella risultati deve essere vuota.")
    bed_file = work_dir / "snp_regions.bed"
    generated_pileup = work_dir / "pileup.txt"
    normalized_panel = work_dir / "SNPpanel.tsv"
    for destination in (bed_file, generated_pileup, normalized_panel, work_dir / "input-validation.json",
                        work_dir / "snp-acquisition.json"):
        if destination.exists() or destination.is_symlink():
            raise ValidationError(f"Preparazione già presente: {destination}")

    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_snp_list(panel_rows, normalized_panel)
    warnings = []
    if mode == "pileup":
        acquisition_changes = [key for key, value in scientific.items()
                               if key != "other_fraction_max" and value != defaults("snp-call")[key]]
        if acquisition_changes:
            warnings.append({"code": "input.existing_pileup_acquisition_settings", "path": str(pileup),
                             "row": None, "message": "Pileup esistente: i parametri di acquisizione "
                             "non possono modificarlo: " + ", ".join(acquisition_changes)})
    write_input_report(work_dir, "snp-call", warnings, normalized=[(panel, normalized_panel)])
    command = None
    if mode == "bam":
        write_snp_bed(positions, bed_file)
        pileup = generated_pileup
        command = [
            "samtools", "mpileup", "-f", str(reference), "-l", str(bed_file),
            "--output-QNAME", *samtools_options("snp-call", scientific),
            "--no-output-ins", "--no-output-del", "--no-output-ends",
            "-o", str(pileup), str(bam),
        ]
    return SnpPreparation(command, [
        "--pileup", str(pileup), "--snplist", str(normalized_panel),
        "--out", str(out_dir / "SNPcall_output.txt"),
    ], generated_pileup if mode == "bam" else None, bam, target_lengths, lengths)


if __name__ == "__main__":
    try:
        _run_acquisition(Path(sys.argv[1]), sys.argv[2:])
    except pileup_pool.Cancelled as exc:
        sys.exit(128 + exc.signum)
    except (OSError, ValueError, ValidationError, pileup_pool.PileupError) as exc:
        print(f"SNP acquisition: {exc}", file=sys.stderr)
        sys.exit(1)
