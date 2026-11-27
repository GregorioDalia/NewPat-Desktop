"""Run the three short acceptance cases against an installed NewPat 0.9.99."""
from __future__ import annotations

import argparse
from collections.abc import Callable
import csv
from dataclasses import dataclass
from datetime import datetime
from html import escape
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

REPORT = "Esito-NewPat.html"
TITLES = {
    "prenatale": "CPI prenatale da due BAM",
    "sesso": "Sesso fetale da tabelle DNP e SNP",
    "calling": "Parallelismo del calling su quattro cromosomi",
}
STEPS = {"dnp-call": "DNPcall", "snp-call": "SNPcall", "cpi": "CPI prenatale", "fetal-sex": "Sesso fetale"}


def read(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def optional(path):
    try:
        data = read(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def seconds(value):
    return f"{value:.2f} s" if isinstance(value, (int, float)) else "n.d."


def duration(start, end):
    try:
        value = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        return value if value >= 0 else None
    except (TypeError, ValueError):
        return None


@dataclass
class Case:
    name: str
    arguments: list
    validate: Callable[[Path], str]


def prepare_cases(project, data):
    from installed_models import (check_fetal_sex, combined_fetal_dnp, copy_fetal_sex_fixtures,
                                  fetal_sex_inputs)
    from installed_workflows import check_plan, check_positive_cpi
    from newpat.desktop.examples import save_example_data

    trio = save_example_data(project, data, "it")
    timing = trio / "timing"
    baseline = read(project / "docs/validation/0.9.10-apple-silicon-timing.json")
    fixture = data / "reference-sex"
    copy_fetal_sex_fixtures(project / "tests/fixtures/fetal_sex", fixture)
    sample = "Male_fetus"
    autosomes, x, y = fetal_sex_inputs(fixture, sample)
    dnp = combined_fetal_dnp(autosomes, x, data / "combined")

    def prenatal(run):
        check_positive_cpi(run, contamination=False, snp=False, cutoffs=False)
        return "Tre loci con conteggi materni 96/4 e paterni 50/50. Frazione fetale 8%, CPI 8."

    def sex(run):
        root, _, _ = check_plan(run, ["fetal-sex"])
        result = check_fetal_sex(root / "steps/fetal_sex", fixture, sample)
        return f"Esito {result['fetal_sex']}. Tutte e quattro le tabelle coincidono con l’esempio di riferimento."

    def calling(run):
        _, _, state = check_plan(run, ["dnp-call", "snp-call"])
        for step in state["steps"]:
            kind = {"dnp-call": "dnp", "snp-call": "snp"}[step["workflow"]]
            artifact, = step["artifacts"][kind + "-tables"]
            require(artifact["sample"] == "sample1" and artifact["sha256"] == baseline["table_sha256"][kind],
                    f"La tabella {kind.upper()} differisce dal risultato di riferimento.")
        return "Le tabelle finali DNP e SNP coincidono con i due SHA-256 di riferimento."

    return [
        Case("prenatale", ["workflow", "dnp-cpi", "--pair", "family_a", trio / "alignments/mother.bam",
                          trio / "alignments/father.bam", "--reference", trio / "reference/synthetic.fa",
                          "--panel", trio / "panels/dnp.tsv", "--popfreq", trio / "frequencies/dnp.tsv"], prenatal),
        Case("sesso", ["workflow", "analyze", "--caller", "tables", "--fetal-sex", "maternal",
                      dnp, y], sex),
        Case("calling", ["workflow", "analyze", "--caller", "both", "--sample", "sample1", timing / "timing.bam",
                        "--reference", timing / "reference.fa", "--dnp-panel", timing / "dnp.tsv",
                        "--snp-panel", timing / "snp.tsv"], calling),
    ]


def process_window(processes):
    if not processes:
        return None
    intervals = [(item.get("started_at_unix"), item.get("finished_at_unix")) for item in processes]
    if any(not isinstance(t, (int, float)) for interval in intervals for t in interval):
        return None
    if any(end < start for start, end in intervals):
        return None
    return max(end for _, end in intervals) - min(start for start, _ in intervals)


def parallel_verdict(observations):
    if not observations:
        return "Nessuna misura disponibile."
    observed = [item[3] for item in observations]
    if any(value is not None and value > 1 for value in observed):
        return "Più processi simultanei osservati."
    if any(planned and planned > 1 and peak == 1 for _, _, planned, peak, _ in observations):
        return "Da verificare. Il motore aveva previsto più processi ma il picco osservato è uno."
    if any(value is None or value < 1 for value in observed):
        return "Misure incomplete. Il parallelismo non è verificabile per tutte le fasi."
    return "Un processo osservato per fase. Il motore ha lavorato in serie nelle fasi misurate."


def measurements(run):
    from newpat.run_report import _parallel_section

    record = optional(run / "run.json")
    root = run / "output/workflow"
    state = optional(root / "workflow-state.json")
    budget = record.get("resource_budget") or {}
    rows = []
    observations = []
    for step in state.get("steps", []):
        kind = step["workflow"]
        work = root / "steps" / step["id"] / "work"
        rows.append([STEPS.get(kind, kind), seconds(duration(step.get("started_utc"), step.get("finished_utc"))),
                     "—", "—", step.get("status", "n.d.")])
        if kind in ("dnp-call", "snp-call"):
            label = "DNP" if kind == "dnp-call" else "SNP"
            acquisition = optional(work / ("dnp-pileup.json" if kind == "dnp-call" else "snp-acquisition.json"))
            pool = acquisition.get("parallel") or {}
            elapsed = acquisition.get("elapsed_seconds")
            phase = label + " · pileup samtools"
            if kind == "snp-call":
                phase += " (dal primo avvio all’ultima uscita)"
                elapsed = process_window(acquisition.get("processes"))
            observations.append((phase, elapsed,
                                 pool.get("workers"), pool.get("observed_max_processes"), pool.get("reason")))
        if kind == "dnp-call":
            blocks = optional(work / "dnp-blocks.json")
            rows.append(["DNP · indicizzazione del pileup", seconds(blocks.get("index_seconds")), "—", "—", ""])
            observations.append(("DNP · calcolo R", blocks.get("processing_seconds"), blocks.get("workers"),
                                 blocks.get("observed_workers"), blocks.get("scheduling_strategy")))
        if kind == "snp-call":
            timing_file = work.parent / "output/summary/resources.tsv"
            try:
                with timing_file.open(encoding="utf-8") as stream:
                    snp_elapsed = float(next(csv.DictReader(stream, delimiter="\t"))["seconds"])
            except (OSError, KeyError, ValueError, StopIteration):
                snp_elapsed = None
            rows.append(["SNP · calcolo R e scrittura dei risultati", seconds(snp_elapsed), "—", "—", ""])
    for label, elapsed, planned, observed, reason in observations:
        if observed is None:
            note = "Picco non misurato"
        elif observed > 1:
            note = "Parallelo osservato"
        elif observed == 1 and planned and planned > 1:
            note = "Previsti più processi, osservato uno"
        elif observed == 1:
            note = "Un processo osservato"
        else:
            note = "Nessun processo registrato"
        rows.append([label, seconds(elapsed), planned, observed, note + (f" ({reason})" if reason else "")])
    details = _parallel_section(run, record) if observations else ""
    return {"rows": rows, "details": details, "parallel": parallel_verdict(observations),
            "cpu": budget.get("cpu_limit"), "ram": budget.get("memory_capacity_mib")}


def table(headers, rows):
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{escape(str(c)) if c is not None else 'n.d.'}</td>" for c in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def write_report(output, report):
    def field(key):
        return escape(str(report.get(key) or "n.d."))

    parts = ['<!doctype html><html lang="it"><meta charset="utf-8"><title>Mini-suite NewPat</title>',
             '<meta name="viewport" content="width=device-width,initial-scale=1"><style>'
             'body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#182f31}'
             'table{border-collapse:collapse;margin:.6rem 0;width:100%}td,th{text-align:left;vertical-align:top;'
             'padding:.35rem .6rem;border-bottom:1px solid #ccd8d6}th{background:#eaf2f0}details{margin:1rem 0}'
             'h1,h2,h3{line-height:1.2}code{overflow-wrap:anywhere}</style><main>',
             f"<h1>Mini-suite NewPat · {field('status')}</h1>",
             f"<p>Versione {field('version')} · macOS {field('macos')} · {field('machine')}<br>"
             f"Build <code>{field('commit')}</code></p>",
             f"<p>Preparazione del runtime {seconds(report.get('prepare'))} · "
             f"Tempo totale trascorso {seconds(report.get('total'))}</p>"]
    if report.get("error"):
        parts.append(f"<p>{field('error')}</p>")
    parts.append(table(["Prova", "Esito", "Tempo del comando", "Riscontro"], [
        [TITLES[name], row["status"], seconds(row.get("wall")), row.get("result", "—")]
        for name, row in report["cases"].items()]))
    probe = report["cases"].get("calling", {})
    if "metrics" in probe:
        parts.append("<p><strong>Parallelismo sul BAM a quattro cromosomi</strong> · "
                     + escape(probe["metrics"]["parallel"]) + "</p>")
    for name, row in report["cases"].items():
        if "metrics_error" in row:
            parts.append(f"<p>{TITLES[name]} · Misure incomplete. {escape(row['metrics_error'])}</p>")
        if "metrics" not in row:
            continue
        data = row["metrics"]
        parts.append(f"<h2>{TITLES[name]}</h2>")
        if data["cpu"] is not None or data["ram"] is not None:
            ram = f"{data['ram']:.0f}" if isinstance(data['ram'], (int, float)) else "n.d."
            parts.append(f"<p>Capacità del motore · CPU {escape(str(data['cpu'] or 'n.d.'))} · RAM {ram} MiB</p>")
        if data["rows"]:
            parts.append(table(["Fase", "Durata", "Processi previsti", "Picco osservato", "Osservazione"], data["rows"]))
        else:
            parts.append("<p>Tempi delle fasi non disponibili.</p>")
        if name == "sesso":
            parts.append("<p>Le tabelle contengono già i conteggi. Il pileup BAM e i relativi processi samtools "
                         "non si applicano a questa prova.</p>")
        if data["details"]:
            parts.append("<details><summary>Dettaglio degli eventi dei processi</summary>" + data["details"] + "</details>")
    parts.append("<p>Il PASS richiede la corrispondenza dei risultati scientifici. Ogni prova viene "
                 "eseguita una volta, con parallelismo automatico. I tempi delle sottofasi possono "
                 "sovrapporsi. Il tempo del comando include l’avvio. n.d. indica una misura assente.</p></main></html>")
    temporary = output / (REPORT + ".tmp")
    temporary.write_text("\n".join(parts), encoding="utf-8")
    temporary.replace(output / REPORT)


def launch(launcher, arguments, log):
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run([launcher, *arguments], stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
    require(result.returncode == 0, f"Il comando è terminato con codice {result.returncode}. Registro locale {log.name}.")


def run_suite(project, output, expected_commit=None):
    started = time.monotonic()
    report = {"status": "IN CORSO", "macos": platform.mac_ver()[0], "machine": platform.machine(),
              "cases": {name: {"status": "NON ESEGUITO"} for name in TITLES}}
    launcher = project.parent / "NewPat.command"

    def message(exc):
        return (str(exc) or type(exc).__name__).replace(str(output), "<prova>").replace(str(Path.home()) + "/", "~/")

    def save():
        report["total"] = time.monotonic() - started
        write_report(output, report)

    try:
        save()
        manifest = read(project / ".distribution/macos-manifest.json")
        report.update(version=manifest["version"], commit=manifest["source_commit"])
        require(sys.platform == "darwin" and platform.machine() == manifest.get("architecture") == "arm64"
                and manifest.get("scientific_platform") == "linux/arm64" and manifest["version"] == "0.9.99",
                "Questa mini-suite richiede NewPat 0.9.99 per Mac Apple Silicon.")
        if expected_commit:
            require(expected_commit.read_text().strip() == report["commit"], "La build installata differisce dal kit.")
        sys.path[:0] = [str(project / "src"), str(project / "scripts/acceptance")]
        from installed_suite import verify_run

        print("Preparazione del runtime NewPat…", flush=True)
        before = time.monotonic()
        try:
            launch(launcher, ["--runtime", "prepare"], output / "preparazione.log")
        finally:
            report["prepare"] = time.monotonic() - before
        state = read(Path.home() / "Library/Application Support/NIPAT-Desktop/.runtime/macos/runtime.json")
        require(state.get("phase") == "ready" and state.get("source_commit") == report["commit"]
                and re.fullmatch(r"sha256:[0-9a-f]{64}", state.get("runtime_image") or ""),
                "Il runtime preparato non corrisponde alla build installata.")
        inputs = output / "dati"
        inputs.mkdir()
        runs = output / "run"
        for case in prepare_cases(project, inputs):
            print(TITLES[case.name] + "…", flush=True)
            row = report["cases"][case.name]
            row["status"] = "IN CORSO"
            save()
            run = runs / case.name
            try:
                before = time.monotonic()
                try:
                    launch(launcher, ["--runs-dir", runs, "--data-dir", inputs, "--execution-mode", "auto",
                                      *case.arguments, "--run-name", case.name], output / (case.name + ".log"))
                finally:
                    row["wall"] = time.monotonic() - before
                verify_run(run, state["runtime_image"])
                record = read(run / "run.json")
                require(record["runtime"]["architecture"] == "arm64"
                        and record["execution_options"]["execution_mode"] == "auto"
                        and record["execution_options"]["performance_diagnostics"] is False,
                        "Architettura o modalità di esecuzione inattesa.")
                row["result"] = case.validate(run)
                row["status"] = "PASS"
            except Exception as exc:
                row.update(status="FAIL", result=message(exc))
                failed = optional(run / "run.json")
                for command in failed.get("commands", []):
                    if command.get("returncode"):
                        row["result"] += f" Codice del runtime {command['returncode']}."
                for step in optional(run / "output/workflow/workflow-state.json").get("steps", []):
                    if step.get("status") in ("running", "failed", "interrupted"):
                        row["result"] += f" Fase {STEPS.get(step.get('workflow'), step.get('id'))}."
            try:
                row["metrics"] = measurements(run)
            except Exception as exc:
                row["metrics_error"] = message(exc)
            print(f"{row['status']} · {seconds(row['wall'])}", flush=True)
            save()
        report["status"] = "PASS" if all(r["status"] == "PASS" for r in report["cases"].values()) else "FAIL"
    except KeyboardInterrupt:
        report.update(status="INTERROTTO", error="Esecuzione interrotta.")
        for row in report["cases"].values():
            if row["status"] == "IN CORSO":
                row["status"] = "INTERROTTO"
    except Exception as exc:
        report.update(status="FAIL", error=message(exc))
    finally:
        save()
        print(f"{report['status']} · Report da inviare: {output / REPORT}", flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--source-commit-file", type=Path)
    options = parser.parse_args()
    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="NewPat-Mini-", dir=downloads))
    raise SystemExit(run_suite(options.project, directory, options.source_commit_file))
