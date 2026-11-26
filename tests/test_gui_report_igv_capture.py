"""Offline PDF figure using IGV's real BAM decoding and native SVG rendering."""
import base64
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def verify_report_igv_capture(page, app, check):
    data = ROOT / "examples" / "synthetic-trio"
    names = ["mother", "father", "child"]
    prepared = app.prepare_igv({
        "reference": {"fasta": str(data / "reference/synthetic.fa")},
        "tracks": [{"path": str(data / f"alignments/{name}.bam"), "name": name} for name in names],
        "locus": "chrDnpSynthetic:30-74",
    })
    prepared.update(available=True, site="chrDnpSynthetic:50-51", marker="DNP", build="synthetic")
    navigation = page.evaluate("NipatIGV.getNavigation()")
    capture = "options => window.NewPatReportIGV.capture(options, {language:'en'})"
    view = page.evaluate(capture, prepared)
    check(bool(view) and view["tracks"] == names and view["locus"] == prepared["locus"] and
          view["site"] == prepared["site"] and view["build"] == "synthetic",
          "The PDF figure captures the indexed trio BAMs over the selected two-base DNP")
    png = base64.b64decode(view["image"].removeprefix("data:image/png;base64,"), validate=True)
    width, height = struct.unpack(">II", png[16:24])
    check(png.startswith(b"\x89PNG\r\n\x1a\n") and 450 < width < 1800 and 150 < height < 1100 and
          len(view["image"]) <= 750_000, "IGV renders a bounded PNG suitable for the offline PDF")
    signal = page.evaluate("""async source => {
        const image=new Image(); image.src=source; await image.decode();
        const c=document.createElement('canvas'); c.width=image.width; c.height=image.height;
        const ctx=c.getContext('2d'); ctx.drawImage(image,0,0);
        const data=ctx.getImageData(0,0,c.width,c.height).data;
        let bases=0, greys=0;
        for(let i=0;i<data.length;i+=4){
            const r=data[i],g=data[i+1],b=data[i+2];
            if(Math.max(r,g,b)-Math.min(r,g,b)>80) bases++;
            if(r===g&&g===b&&r>100&&r<200) greys++;
        }return [bases,greys];
    }""", view["image"])
    check(min(signal) > 100, "The genuine IGV figure contains coloured bases and grey read or coverage glyphs")
    single = {**prepared, "site": "chrDnpSynthetic:50", "marker": "SNP", "tracks": prepared["tracks"][:1]}
    check(bool(page.evaluate(capture, single)), "A one-base result uses its own sample's alignment")
    missing = {**prepared, "locus": "chrDnpSynthetic:1-55", "site": "chrDnpSynthetic:5-6"}
    check(page.evaluate(capture, missing) is None,
          "Nearby reads without a read covering the selected site do not produce an IGV figure")
    distant = {**prepared, "locus": "chrDnpSynthetic:30-165", "site": "chrDnpSynthetic:50-140"}
    check(page.evaluate(capture, distant) is None,
          "Separate reads at two coordinates cannot be reported as one read spanning both DNP bases")
    foreign = dict(prepared, tracks=[dict(prepared["tracks"][0], url="https://example.invalid/sample.bam")])
    check(page.evaluate(capture, foreign) is None, "A report capture rejects a non-local alignment before loading IGV")
    cancelled = page.evaluate("""async prepared => {
        const c=new AbortController(), job=NewPatReportIGV.capture(prepared,{signal:c.signal});
        c.abort();return await job;
    }""", prepared)
    check(cancelled is None and page.locator('iframe[src="report-igv.html"]').count() == 0 and
          page.evaluate("NipatIGV.getNavigation()") == navigation,
          "Capture cleanup releases its isolated viewer and preserves the interactive IGV session")
    verify_archived_report_pdf(page, app, check)


def verify_archived_report_pdf(page, app, check):
    """Native-shaped synthetic oracle archive plus the shipped indexed BAMs, through the save dialog."""
    from nipat.execution.tracking import file_evidence
    from test_gui_results import artifact, table, validation, write_json

    data = ROOT / "examples" / "synthetic-trio"
    reference = data / "reference/synthetic.fa"
    index = Path(str(reference) + ".fai")
    names = ("mother", "father", "child")
    bams = [data / f"alignments/{name}.bam" for name in names]
    records = [file_evidence(path) for path in [reference, index, *bams, *(Path(str(p) + ".bai") for p in bams)]]
    runs = app.service.layout.runs_dir
    runs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runs, prefix="report-igv-") as directory, tempfile.TemporaryDirectory() as output:
        run, target = Path(directory), Path(output) / "detailed.pdf"
        mapping = [{"sample_id": name, "original_path": str(path)} for name, path in zip(names, bams)]
        write_json(run / "run.json", {"schema_version": 1, "workflow": "cpin", "status": "succeeded",
                   "run_name": "Synthetic trio report", "inputs": records, "started_at": "2026-11-25T09:00:00Z",
                   "parameters": {"marker_type": "DNP", "sample_mapping": mapping}})
        write_json(run / "gui.json", {"schema_version": 1, "draft": {
                   "reference": str(reference), "reference_genome": {"build": "custom", "fasta": str(reference),
                       "index": str(index), "fasta_sha256": records[0]["sha256"], "index_sha256": records[1]["sha256"]},
                   "samples": [{"id": n, "kind": "bam", "path": str(b)} for n, b in zip(names, bams)]}})
        table(run / "output/Summary_Postnatal_CPI.txt",
              ["Trio", "Marker_type", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites",
               "No_obligatory_allele_sites", "Mismatch_probability"], [["trio1", "DNP", 8, 0.903089986991944, 3, 3, 0, 0, 0.001]])
        relative = "output/trio1_sites.txt"
        table(run / relative, ["chr", "pos1", "pos2", "Status", "Paternity_Index", "Paternity_status"],
              [["chrDnpSynthetic", start, start + 1, "eligible", 2, "match"] for start in (50, 140, 230)])
        validation(run, "cpin", {"cpin-trios": [{"trio": "trio1", "native_trio": "trio1",
                   "sites": artifact(run, relative), **{role: {"sample": role} for role in names}}]})
        page.locator('nav [data-view="archive"]').click()
        page.locator(f'[data-action="open-run"][data-id="{run.name}"]').click()
        page.locator('[data-action="choose-report"]').first.click()
        dialog = page.get_by_role("dialog")
        dialog.locator("#report-detailed").check()
        picker = SimpleNamespace(save_file=lambda *_: target)
        with patch.object(app, "host", picker):
            dialog.locator('[data-action="save-report"]').click()
            dialog.wait_for(state="detached")
        check(target.read_bytes().startswith(b"%PDF-"), "Exporting the archived trio with its indexed reads produces a PDF")
        if shutil.which("pdfimages"):
            images = subprocess.check_output(["pdfimages", "-list", str(target)], text=True)
            # The wordmark is also an image; require a separate large IGV raster.
            rows = [line.split() for line in images.splitlines()[2:]]
            check(any(r[2] == "image" and int(r[3]) > 600 and int(r[4]) > 180 for r in rows),
                  "The saved PDF contains the rendered alignment image as an embedded raster")
        if shutil.which("pdftotext"):
            text = subprocess.check_output(["pdftotext", "-layout", str(target), "-"]).decode()
            check("chrDnpSynthetic:50-51" in text and "mother, father, child" in text
                  and ("Riga dati 1" in text or "Data row 1" in text),
                  "The PDF caption identifies the actual DNP site, its archived row and the three case-specific tracks")
        page.locator('nav [data-view="archive"]').click()


def test_offline_report_igv_capture(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = next((exe for name in ("chromium", "google-chrome", "chromium-browser")
                     if (exe := shutil.which(name))), None)
    if not chromium:
        pytest.skip("System Chromium is required for this browser test")
    from nipat.gui.app import DesktopApplication

    from nipat.gui.service import GuiService
    from nipat.paths import ProjectLayout
    from nipat.preferences import PreferencesStore

    layout = ProjectLayout.discover(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data")
    app = DesktopApplication(host=object(), service=GuiService(layout, preferences_store=PreferencesStore(tmp_path / "settings.json")))

    def check(passed, message):
        assert passed, message

    with app.server, playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(app.server.url)
        verify_report_igv_capture(page, app, check)
        browser.close()
