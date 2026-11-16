"""Exercise the shipped UI, HTTP service and bundled IGV with real indexed local data.

Linux CI uses a system Chromium/Chrome through Playwright. Native window smoke
checks remain separate. Only native file dialogs are replaced by a deterministic
picker; RPC and genomic decoding/rendering are production code. A non-executing
Job fixture checks progress rendering without claiming a scientific analysis.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from nipat import __version__
from nipat.gui.app import DesktopApplication
from nipat.gui.jobs import Job
from nipat.gui.plan import prepare_analysis
from nipat.gui.service import GuiService
from nipat.paths import ProjectLayout
from nipat.preferences import PreferencesStore
from test_gui_igv import create_alignment_fixture


class FixturePicker:
    """Replace only the operating-system picker, preserving its real RPC route."""

    def __init__(self):
        self.paths: list[Path] = []

    def pick_files(self, _title, _filters, _multiple):
        return self.paths

    def pick_directory(self, _title):
        return self.paths[0] if self.paths else None

    def save_file(self, _title, _name, _filters):
        raise AssertionError("This verification does not export files through a native dialog")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_files(paths):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def prepare_fixture(directory):
    data = directory / "data"
    selection = create_alignment_fixture(data)
    layout = ProjectLayout(ROOT, directory, data, directory / "runs", ROOT / "compose.yaml")
    panel = data / "panel.tsv"
    panel.write_text("1\t151\t152\tGT\tAT\n", encoding="utf-8")
    draft = {"name": "Verifica interfaccia", "caller": "dnp",
             "samples": [{"id": "Synthetic", "kind": "bam", "path": selection["tracks"][0]["path"]}],
             "branches": {"DNP": [], "SNP": []}, "reference": selection["reference"]["fasta"],
             "resources": {"DNP": {"panel": str(panel)}, "SNP": {}},
             "families": {"cpi": [], "cpin": []}, "scientific_settings": {}, "execution": {}}
    prepared = prepare_analysis(draft, layout)
    service = GuiService(layout, preferences_store=PreferencesStore(directory / "settings/preferences.json"))
    service.ui_save({"language": "it", "reduce_motion": False})
    job = Job(prepared)
    job.status = "running"
    job.log("UI verification fixture: no scientific calculation is running.")
    service.jobs._jobs[job.id] = job
    run = layout.runs_dir / "archived-ui-fixture"
    write_json(run / "run.json", {"schema_version": 1, "workflow": "dnp-call", "status": "interrupted",
               "run_name": "Esperimento interrotto · verifica UI", "started_at": "2026-11-15T10:00:00Z",
               "finished_at": "2026-11-15T10:01:00Z", "source": {"nipat_version": __version__},
               "parameters": {"marker_type": "DNP", "sample_mapping": [{"sample_id": "Synthetic",
                   "original_path": selection["tracks"][0]["path"]}]}})
    write_json(run / "gui.json", {"schema_version": 1, "name": "Esperimento interrotto · verifica UI", "draft": draft})
    output = run / "output" / "DNPcall_output.txt"
    output.parent.mkdir()
    output.write_text("chr\tpos1\tpos2\tGT\ttotal_count\n1\t151\t152\t0/1\t20\n", encoding="utf-8")
    preserved = list(data.iterdir()) + [run / "run.json", run / "gui.json", output]
    return service, job, selection, run, preserved


READS = """() => {
 const instance=window.__qaIgv;
 const view=instance?.trackViews.find(v=>v.track.type==='alignment'||v.track.config?.format==='bam');
 const viewport=view?.viewports?.[0], features=viewport?.cachedFeatures;
 if(!features || typeof features.allAlignments!=='function')return null;
 const reads=features.allAlignments().map(read=>({name:read.readName,start:read.start+1,length:read.lengthOnRef}));
 const canvas=viewport.canvas,context=canvas?.getContext('2d');let colouredPixels=0;
 if(context){const image=context.getImageData(0,0,canvas.width,canvas.height);for(let i=0;i<image.data.length;i+=4){if(image.data[i+3]&&Math.min(image.data[i],image.data[i+1],image.data[i+2])<230)colouredPixels++}}
 return {reads,canvas:!!canvas,colouredPixels,coverageMaximum:features.coverageMap?.maximum||null};
}"""


class BrowserProbe:
    """Read the page through DevTools without weakening its production CSP.

    Playwright's wait_for_function uses eval inside the main world. NIPAT
    deliberately forbids unsafe-eval there. DevTools evaluates only these test
    expressions; ordinary scripts, requests and CSP remain unchanged.
    """

    def __init__(self, page):
        self.page = page
        self.session = page.context.new_cdp_session(page)

    def evaluate(self, expression):
        expression = expression.strip()
        if expression.startswith("() =>"):
            expression = "(" + expression + ")()"
        result = self.session.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
            "allowUnsafeEvalBlockedByCSP": True,
        })
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise AssertionError(details.get("exception", {}).get("description") or details.get("text"))
        return result["result"].get("value")

    def wait(self, expression, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            self.page.wait_for_timeout(100)
        raise AssertionError("Timed out waiting for UI condition: " + expression[:200])


def run_verification(report_path, executable):
    from playwright.sync_api import sync_playwright

    report_path.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"schema_version": 1, "status": "failed", "nipat_version": __version__,
                "scope": "Actual browser rendering, production DesktopApplication/GuiService/HTTP and bundled IGV; synthetic indexed alignment fixture, not domain or native-host acceptance.",
                "checks": [], "screenshots": [], "errors": [], "external_requests": []}
    page = None
    token = ""
    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        evidence["checks"].append(description)

    try:
        with tempfile.TemporaryDirectory(prefix="nipat-gui-interactions-") as temporary:
            directory = Path(temporary)
            service, job, selection, archived, preserved = prepare_fixture(directory)
            before = digest_files(preserved)
            picker = FixturePicker()
            app = DesktopApplication(service=service, host=picker)
            token = app.server.token
            with app.server, sync_playwright() as playwright, ExitStack() as cleanup:
                browser = playwright.chromium.launch(executable_path=executable, headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"])
                evidence["browser_version"] = browser.version
                page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
                page.set_default_timeout(30000)
                probe = BrowserProbe(page)
                def capture_failure():
                    if evidence["status"] != "passed":
                        try:
                            failure = report_path.parent / "failure.png"
                            page.screenshot(path=str(failure), full_page=True, timeout=5000)
                            evidence["screenshots"].append(failure.name)
                        except Exception:
                            pass
                cleanup.callback(capture_failure)
                page.on("request", lambda request: evidence["external_requests"].append(request.url)
                        if request.url.startswith(("http://", "https://")) and not request.url.startswith(f"http://{app.server.host}/") else None)
                page.on("pageerror", lambda error: evidence["errors"].append(str(error)))
                def console_message(message):
                    if message.type == "error" and "favicon.ico" not in message.location.get("url", ""):
                        evidence["errors"].append(message.text)
                page.on("console", console_message)
                page.goto(app.server.url)
                probe.wait("document.documentElement.dataset.nipatReady==='true'")
                check(page.locator("#version").inner_text().startswith(__version__), "Displayed application version matches source")
                page.locator('[data-action="navigate"][data-view="activity"]').click()
                page.wait_for_selector('[data-job-card] .dna-rung')
                check(page.locator('.dna-rung').count() == 10, "Recognizable DNA helix contains ten rungs")
                probe.evaluate("window.__qaDna=document.querySelector('.dna-loader');window.__qaAnimation=window.__qaDna.querySelector('.dna-rung').getAnimations()[0]")
                progress = probe.evaluate("() => {const node=document.querySelector('.progress-track span');return {inline:node.style.width,width:node.getBoundingClientRect().width}}")
                check(not progress["inline"] and progress["width"] > 0, "Unknown progress band is visible without zero-width override")
                probe.wait("window.__qaAnimation && window.__qaAnimation.currentTime>1800")
                check(probe.evaluate("window.__qaDna===document.querySelector('.dna-loader')&&window.__qaAnimation===document.querySelector('.dna-rung').getAnimations()[0]"), "Polling preserves the live DNA node and running animation")
                with job.lock:
                    job.progress = {"phase": "pileup", "completed": 1, "total": 4, "workflow": "dnp-call"}
                probe.wait("document.querySelector('.progress-track').getAttribute('aria-valuenow')==='25'")
                check(probe.evaluate("window.__qaDna===document.querySelector('.dna-loader')"), "Measured phase progress updates without remounting DNA")
                activity = report_path.parent / "activity.png"
                page.screenshot(path=str(activity), full_page=True)
                evidence["screenshots"].append(activity.name)
                page.emulate_media(reduced_motion="reduce")
                check(probe.evaluate("getComputedStyle(document.querySelector('.dna-rung')).animationName") == "none", "Operating-system reduced-motion preference disables DNA animation")
                page.emulate_media(reduced_motion="no-preference")
                with job.lock:
                    job.status = "interrupted"
                    job.finished_at = datetime.now(timezone.utc).isoformat()
                    job.done.set()

                # Observe the real returned instance; delegate unchanged to the bundled renderer.
                # IGV 3.8.9 does not export a browser-inventory function.
                probe.evaluate("""() => {const create=window.igv.createBrowser;window.igv.createBrowser=async function(...args){const instance=await create.apply(this,args);window.__qaIgv=instance;return instance}}""")
                page.locator('[data-action="navigate"][data-view="igv"]').click()
                picker.paths = [Path(selection["reference"]["fasta"])]
                page.locator('[data-action="choose-path"][data-key="igv-reference.fasta"]').click()
                page.locator('[data-action="igv-add-track"]').click()
                picker.paths = [Path(selection["tracks"][0]["path"])]
                page.locator('[data-action="choose-path"][data-key="igv-track.0.path"]').click()
                page.locator('[data-action="igv-load"]').click()
                probe.wait("window.NipatApp.state.igv.loaded")
                discovered = probe.evaluate("({reference:NipatApp.state.igv.reference,tracks:NipatApp.state.igv.tracks})")
                check(discovered["reference"]["index"].endswith(".fa.fai") and discovered["tracks"][0]["index"].endswith(".bam.bai"), "Reference and BAM indices discovered through actual backend")
                check(page.locator('#igv-chromosome').input_value() == "all", "Initial custom navigation shows whole-genome overview")
                check(probe.evaluate("[...document.querySelectorAll('#igv-container .igv-navbar-genomic-location')].every(n=>getComputedStyle(n).display==='none')"), "Duplicate native locus controls are hidden")
                check(page.get_by_text("Select Tracks", exact=True).is_visible(), "IGV track display tools remain available")
                page.locator('#igv-chromosome').select_option('1')
                probe.wait("NipatIGV.getNavigation().chromosome==='1'")
                page.locator('#igv-locus').fill(selection["locus"])
                page.locator('[data-action="igv-search"]').click()
                probe.wait("NipatIGV.getNavigation().start===80&&NipatIGV.getNavigation().end===260")
                probe.wait("(" + READS + ")()?.reads.length===20")
                observed = probe.evaluate(READS)
                expected = json.loads((directory / "data/fixture.json").read_text())["expected_reads"]
                check(sorted(observed["reads"], key=lambda read: read["name"]) == expected, "Bundled IGV decodes all twenty expected alignments with exact names, positions and lengths")
                check(observed["canvas"] and observed["colouredPixels"] > 100, "Alignment viewport paints nonempty graphical content")
                evidence["alignment_evidence"] = observed
                covered = probe.evaluate("NipatIGV.getNavigation()")
                page.locator('[data-action="igv-zoom-in"]').click()
                probe.wait("NipatIGV.getNavigation().end-NipatIGV.getNavigation().start<180")
                check(page.locator('#igv-locus').input_value() == probe.evaluate("NipatIGV.getNavigation().locus"), "Zoom synchronizes the visible location field")
                page.locator('[data-action="igv-back"]').click()
                probe.wait("NipatIGV.getNavigation().start===80&&NipatIGV.getNavigation().end===260")
                check(page.locator('#igv-locus').input_value() == covered["locus"], "Previous-region control restores the covered interval")
                before_invalid = probe.evaluate("NipatIGV.getNavigation().locus")
                page.locator('#igv-locus').fill('23')
                page.locator('[data-action="igv-search"]').click()
                probe.wait("document.querySelector('#toast').textContent.includes('regione non è disponibile')")
                check(probe.evaluate("NipatIGV.getNavigation().locus") == before_invalid, "Invalid chromosome 23 gives a clear error without moving the viewer")
                page.locator('[data-action="igv-all"]').click()
                probe.wait("NipatIGV.getNavigation().wholeGenome")
                check(page.locator('#igv-locus').input_value() == 'all', "Whole-genome button restores and synchronizes overview")
                page.locator('[data-action="igv-back"]').click()
                probe.wait("NipatIGV.getNavigation().start===80")
                probe.wait("!document.querySelector('#toast').classList.contains('visible')")
                igv = report_path.parent / "igv-alignments.png"
                page.screenshot(path=str(igv), full_page=True)
                evidence["screenshots"].append(igv.name)

                page.locator('[data-action="navigate"][data-view="archive"]').click()
                page.locator('[data-action="open-run"][data-id="archived-ui-fixture"]').click()
                page.wait_for_selector('[data-action="reuse-run"]')
                page.locator('[data-action="reuse-run"]').first.click()
                probe.wait("NipatApp.state.view==='new'")
                reused = probe.evaluate("NipatApp.state.draft")
                check(reused["samples"][0]["path"] == selection["tracks"][0]["path"] and reused["reference"] == selection["reference"]["fasta"], "Run again opens original recorded input selections")
                page.locator('[data-action="navigate"][data-view="archive"]').click()
                page.locator('[data-action="remove-run"][data-id="archived-ui-fixture"]').click()
                check('file di input resteranno' in page.locator('[role="dialog"]').inner_text(), "Removal confirmation explains source and result preservation")
                page.locator('[data-action="confirm-remove-run"]').click()
                probe.wait("!NipatApp.state.runs.some(run=>run.id==='archived-ui-fixture')")
                check(archived.is_dir() and digest_files(preserved) == before, "Remove from list preserves every source, index, result and metadata byte")
                check(not evidence["external_requests"], "All browser resources and genomic byte ranges stay on the local service")
                check(not evidence["errors"], "No JavaScript exceptions or unexpected browser console errors")
                evidence["status"] = "passed"
                browser.close()
    except Exception as error:
        evidence["failure"] = str(error).replace(token, "[session]") if token else str(error)
        if page is not None:
            try:
                failure = report_path.parent / "failure.png"
                page.screenshot(path=str(failure), full_page=True, timeout=5000)
                evidence["screenshots"].append(failure.name)
            except Exception:
                pass
        raise
    finally:
        if token:
            evidence["errors"] = [error.replace(token, "[session]") for error in evidence["errors"]]
        write_json(report_path, evidence)
        print(json.dumps({"status": evidence["status"], "checks": len(evidence["checks"]), "report": str(report_path)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/gui-interactions/report.json")
    parser.add_argument("--browser", default=None, help="System Chrome/Chromium executable")
    args = parser.parse_args()
    executable = args.browser or next((path for name in ("google-chrome", "chromium", "chromium-browser") if (path := shutil.which(name))), None)
    if not executable:
        parser.error("A system Chrome/Chromium executable is required")
    run_verification(args.report.resolve(), executable)


if __name__ == "__main__":
    main()
