"""Exercise the shipped UI, HTTP service and bundled IGV with real indexed local data.

Linux CI uses a system Chromium/Chrome through Playwright. Native window smoke
checks remain separate. Native file dialogs and the external-browser handoff are observed with test doubles.
RPC and genomic decoding/rendering are production code. A non-executing job
checks progress rendering and an unavailable-runtime fixture checks startup errors.
Recorded CPI/CPIN fixtures exercise plots without recalculating scientific results.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from threading import Event
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from nipat import __version__
from nipat.errors import ValidationError
from nipat.execution.progress import ProgressSnapshot
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


def prepare_curve_fixtures(layout):
    """Write deterministic native-schema result rows, not a scientific calculation."""
    preserved = []
    for module in ("cpi", "cpin"):
        run = layout.runs_dir / f"{module}-curve-ui-fixture"
        native = "MotherM-FatherF_DNPs" if module == "cpi" else "MotherM-FatherF-ChildC_DNPs"
        write_json(run / "run.json", {"schema_version": 1, "workflow": module, "status": "succeeded",
            "run_name": f"{module.upper()} · fixture grafici", "started_at": "2026-11-15T10:00:00Z",
            "finished_at": "2026-11-15T10:01:00Z", "source": {"nipat_version": __version__},
            "parameters": {"marker_type": "DNP", "sample_mapping": []}})
        def write_table(relative, columns, rows):
            target = run / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream, delimiter="," if target.suffix == ".csv" else "\t")
                writer.writerow(columns)
                writer.writerows(rows)
            return {"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        if module == "cpi":
            write_table("output/Summary_FetalFraction_CPI.csv",
                ["Pair", "Median_fetal_fraction_percent", "CPI_medianFF", "N_sites_mother", "N_sites_father"],
                [[native, "6", "0.602", "10", "9"]])
            write_json(run / "output/scientific-settings.json", {"schema_version": 1, "workflow": "cpi",
                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
            curve = write_table(f"output/curves/{native}_panel_1.tsv",
                ["Iteration", "InfSites_mother", "InfSites_father", "CPI", "log_CPI", "Mismatch", "NotMismatch", "Cutoff"],
                [["2", "10", "9", "0.0007525631256789", "-3.123456789012345", "1", "8", "ALL"],
                 ["3", "9", "8", "1", "0", "0", "8", "ALL"],
                 ["4", "8", "7", "NA", "NA", "1", "6", "ALL"]])
            artifacts = {"cpi-pairs": [{"pair": "M:F", "native_pair": native,
                "mother": {"sample": "M"}, "father": {"sample": "F"}, "curves": [{**curve, "cutoff": None}]}]}
        else:
            analysis = "all_compatible_sites"
            write_table("output/Summary_Postnatal_CPI.txt",
                ["Trio", "Analysis", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"],
                [[native, analysis, "0.00046474155109453", "-3.33278849686833", "3", "2", "1"]])
            curve = write_table(f"output/curves/{native}_{analysis}_curve.tsv",
                ["Min_child_reads", "Through_min_child_reads", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"],
                [["2", "5", "-3.33278849686833", "3", "2", "1"],
                 ["6", "6", "-3.42969850987639", "2", "1", "1"],
                 ["7", "10", "0.221848749616356", "1", "1", "0"]])
            artifacts = {"cpin-trios": [{"trio": "family", "native_trio": native,
                "analyses": [{"analysis": analysis, "curve": curve}]}]}
        write_json(run / "work/scientific-validation.json", {"schema_version": 1, "workflow": module,
            "status": "passed", "artifacts": artifacts})
        preserved.extend(path for path in run.rglob("*") if path.is_file())
    return preserved


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
    output = run / "output" / "individual_outputs" / "full_output_sample_0001.txt"
    output.parent.mkdir(parents=True)
    output.write_text("chr\tpos1\tpos2\tGT\ttotal_count\n1\t151\t152\t0/1\t20\n", encoding="utf-8")
    preserved = list(data.iterdir()) + [run / "run.json", run / "gui.json", output] + prepare_curve_fixtures(layout)
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


def verify_language_controls(page, probe, service, check):
    italian = page.get_by_role("radio", name="Italiano", exact=True)
    english = page.get_by_role("radio", name="English", exact=True)
    check(italian.is_checked() and not english.is_checked(), "The active Italian flag has an accessible language name")
    flags = page.locator(".language-picker svg")
    check(flags.count() == 2 and all(flag.is_visible() for flag in flags.all()),
          "Both language flags render as graphics")
    italian.focus()
    with page.expect_response(lambda r: r.request.method == "POST" and
                              r.request.post_data_json.get("method") == "ui.save"):
        italian.press("ArrowRight")
    probe.wait("document.documentElement.lang==='en'")
    check(english.is_checked() and service.ui_get()["language"] == "en",
          "Keyboard language selection persists the English preference in the real service")
    page.reload()
    probe.wait("document.documentElement.dataset.nipatReady==='true'")
    check(english.is_checked() and page.locator('html').get_attribute("lang") == "en",
          "Restarting the interface restores the saved English flag")
    english.focus()
    with page.expect_response(lambda r: r.request.method == "POST" and
                              r.request.post_data_json.get("method") == "ui.save"):
        english.press("ArrowLeft")
    probe.wait("document.documentElement.lang==='it'")


def verify_single_start(page, probe, service, methods, check):
    """Hold the real preview long enough to inspect the pending UI and the duplicate-start guard."""
    release_preview = Event()
    original = service.plan_preview
    error = "Runtime di prova non disponibile. Verifica l’ambiente di esecuzione."

    def slow_preview(draft):
        if not release_preview.wait(timeout=15):
            raise RuntimeError("Verification timed out waiting to release the plan")
        return original(draft)

    def unavailable_runtime(_prepared, _job):
        raise ValidationError(error)

    page.locator('[data-action="step"][data-index="3"]').first.click()
    button = page.locator('[data-action="start-analysis"]')
    check(button.is_enabled(), "Review permits starting directly without a separate preview")
    start = len(methods)
    with patch.object(service, "plan_preview", side_effect=slow_preview), \
         patch.object(service.jobs, "_runner_factory", side_effect=unavailable_runtime):
        try:
            probe.evaluate("""() => {const b=document.querySelector('[data-action=start-analysis]'); b.click();
                document.querySelector('[data-action=start-analysis]').click()}""")
            page.wait_for_selector('.start-check[role="status"]')
            check(button.is_disabled(), "A visible preflight indicator prevents duplicate starts while checking the plan")
        finally:
            release_preview.set()
        probe.wait("NipatApp.state.view==='activity' && NipatApp.state.jobs.some(j=>j.status==='failed')")
        page.get_by_text(error, exact=True).first.wait_for()
    observed = [method for method, _ in methods[start:] if method in {"plan.preview", "analysis.start"}]
    check(observed == ["plan.preview", "analysis.start"],
          "One automatic preview leads to one start and displays the runner's actionable error")
    page.locator('nav [data-view="new"]').click()
    check(probe.evaluate("NipatApp.state.draft.samples.length===0 && !NipatApp.state.draft.reference"),
          "New experiment opens a clean input sheet after an attempted run")


def verify_archive_pages(page, probe, service, methods, check):
    for number in range(30):
        identifier = f"older-{number:02}"
        write_json(service.layout.runs_dir / identifier / "run.json", {
            "schema_version": 1, "workflow": "snp-call", "status": "succeeded",
            "run_name": f"Archive example {number:02}", "started_at": "2001-01-01T00:00:00Z",
            "parameters": {"marker_type": "SNP", "sample_mapping": [{
                "sample_id": f"sample-{number:02}", "original_path": f"{identifier}.bam"}]},
        })

    before = len(methods)
    page.locator('nav [data-view="home"]').click()
    probe.wait("NipatApp.state.recentRuns.length===5")
    check([params for method, params in methods[before:] if method == "runs.list"] == [{"limit": 5, "offset": 0}],
          "Home retrieves five cards in a single bounded request")
    page.locator('nav [data-view="archive"]').click()
    page.wait_for_selector('#archive-results [data-action="archive-page"][data-page="1"]')
    rows = page.locator('#archive-results [data-action="open-run"]')
    check(rows.count() == 25, "The first archive page displays exactly 25 cards")
    page.locator('[data-action="archive-page"][data-page="1"]').click()
    old_card = page.locator('[data-action="open-run"][data-id="older-00"]')
    old_card.wait_for()
    check(rows.count() < 25, "A later archive page includes the oldest experiment")
    search = page.locator("#archive-search")
    search.fill("sample-00")
    probe.wait("NipatApp.state.archiveListing?.total===1 && NipatApp.state.archivePage===0")
    check(old_card.is_visible() and search.evaluate("el => document.activeElement === el"),
          "Searching all pages by sample ID resets pagination and preserves keyboard focus")
    page.select_option("#archive-marker", "DNP")
    page.get_by_text("Nessun esperimento corrisponde ai filtri.", exact=True).wait_for()
    page.select_option("#archive-marker", "SNP")
    old_card.click()
    probe.wait("NipatApp.state.run?.id==='older-00'")
    page.locator("#page-back").click()
    old_card.wait_for()
    check(search.input_value() == "sample-00" and page.locator("#archive-marker").input_value() == "SNP",
          "Returning from the result keeps the query, marker and matching old experiment")


def run_verification(report_path, executable):
    from playwright.sync_api import sync_playwright

    report_path.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"schema_version": 1, "status": "failed", "nipat_version": __version__,
                "scope": "Actual browser rendering, production DesktopApplication/GuiService/HTTP and bundled IGV; synthetic indexed alignment and recorded CPI/CPIN fixtures, not domain or native-host acceptance.",
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
                methods = []
                def record_rpc(request):
                    if request.method == "POST" and request.url == app.server.base_url + "api":
                        body = request.post_data_json
                        methods.append((body["method"], body["params"]))
                page.on("request", record_rpc)
                page.goto(app.server.url)
                probe.wait("document.documentElement.dataset.nipatReady==='true'")
                check(page.locator("#version").inner_text().startswith(__version__), "Displayed application version matches source")
                check(page.locator('.brand img[alt="NewPat"]').evaluate("el => el.complete && el.naturalWidth === 406"),
                      "Desktop displays the packaged Intreccio vector wordmark")
                check(page.locator('main [data-view="new"]').count() == 1,
                      "Home has one create-experiment action above the recent experiments")
                home = report_path.parent / "home.png"
                page.screenshot(path=str(home), full_page=True)
                evidence["screenshots"].append(home.name)
                verify_language_controls(page, probe, service, check)
                page.locator('[data-action="navigate"][data-view="environment"]').click()
                save_examples = page.get_by_role("button", name="Salva dati di esempio")
                picker.paths = [directory]
                save_examples.click()
                examples_dialog = page.get_by_role("dialog", name="Dati di esempio salvati")
                expected_folder = directory / "synthetic-trio"
                check(examples_dialog.locator(".path").inner_text() == str(expected_folder)
                      and (expected_folder / "SHA256SUMS").is_file(),
                      "Example-data button saves the bundled trio locally and shows its destination")
                examples_dialog.locator('[data-action="close-modal"]').click()
                picker.paths = []
                page.locator('[data-action="navigate"][data-view="activity"]').click()
                page.wait_for_selector('[data-job-card] .dna-rung')
                check(page.locator('.dna-rung').count() == 10, "Recognizable DNA helix contains ten rungs")
                check(page.locator('.job-progress .helix').evaluate("el => el.offsetWidth === 40 && el.offsetHeight === 44"),
                      "The running experiment has a compact 40 by 44 pixel helix")
                check(page.locator('.job-header .badge.in-progress svg[aria-hidden="true"]').count() == 1,
                      "Running status includes a distinct icon and readable status label")
                probe.evaluate("window.__qaDna=document.querySelector('.dna-loader');window.__qaAnimation=window.__qaDna.querySelector('.dna-rung').getAnimations()[0]")
                progress = probe.evaluate("() => {const node=document.querySelector('.progress-track span');return {inline:node.style.width,width:node.getBoundingClientRect().width}}")
                check(not progress["inline"] and progress["width"] > 0, "Unknown progress band is visible without zero-width override")
                probe.wait("window.__qaAnimation && window.__qaAnimation.currentTime>1800")
                check(probe.evaluate("window.__qaDna===document.querySelector('.dna-loader')&&window.__qaAnimation===document.querySelector('.dna-rung').getAnimations()[0]"), "Polling preserves the live DNA node and running animation")
                check(page.locator("[data-job-sample]").inner_text() == "Synthetic" and
                      bool(page.locator("[data-job-elapsed]").inner_text()),
                      "Activity shows the sample and elapsed time with the technical log closed")
                log_button = page.locator('[data-action="job-log"]')
                check(log_button.get_attribute("aria-expanded") == "false" and
                      not any(method == "jobs.logs" for method, _ in methods),
                      "Normal progress polling leaves technical logs on demand")
                log_button.click()
                page.locator('[id^="job-log-"]').get_by_text("UI verification fixture", exact=False).wait_for()
                check(log_button.get_attribute("aria-expanded") == "true" and
                      any(method == "jobs.logs" for method, _ in methods),
                      "Opening technical details fetches the real job log")
                log_button.click()
                job.progressed(ProgressSnapshot("running", 2.0, "pileup", ("Synthetic",),
                                                completed=1, total=4, workflow="dnp-call"))
                probe.wait("document.querySelector('.progress-track').getAttribute('aria-valuenow')==='25'")
                check(probe.evaluate("window.__qaDna===document.querySelector('.dna-loader')"), "Measured phase progress updates without remounting DNA")
                check(bool(page.locator('[data-job-phase]').inner_text()) and
                      page.locator('.job-events li').count() == 1,
                      "A phase update appears in the current status and the chronological activity list")
                polls = [params for method, params in methods if method == "jobs.list"]
                check(polls and all(params.get("include_logs") is False for params in polls),
                      "The browser requests summaries when polling jobs")
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
                page.wait_for_selector('[data-job-status="interrupted"]')
                check(page.locator('[data-job-card] .dna-rung').count() == 0 and
                      page.locator('[data-action="cancel-job"]').count() == 0,
                      "Interrupted jobs leave the active experiment controls")
                page.locator('[data-action="remove-job"]').click()
                page.locator('[data-action="confirm-remove-job"]').click()
                page.wait_for_selector('[data-job-card]', state="detached")
                check(not service.jobs.list(), "Dismissing a finished session card also clears its job record")

                # Observe the real returned instance; delegate unchanged to the bundled renderer.
                # IGV 3.8.9 does not export a browser-inventory function.
                probe.evaluate("""() => {const create=window.igv.createBrowser;window.igv.createBrowser=async function(...args){const instance=await create.apply(this,args);window.__qaIgv=instance;return instance}}""")
                page.locator('[data-action="navigate"][data-view="igv"]').click()
                info = page.locator('[data-action="igv-about"]')
                check(info.is_visible() and info.get_attribute("aria-label") and
                      page.locator('h1 + [data-action="igv-about"]').count() == 1,
                      "IGV heading has an accessible information button beside its title")
                local_url = page.url
                with patch("nipat.gui.app.webbrowser.open_new_tab", return_value=True) as open_guide:
                    with page.expect_response(lambda r: r.url == app.server.base_url + "api" and
                                               r.request.post_data_json.get("method") == "igv.about"):
                        info.focus()
                        info.press("Enter")
                    open_guide.assert_called_once_with("https://igv.org/doc/webapp/")
                check(page.url == local_url and len(page.context.pages) == 1,
                      "IGV information hands the official guide to the system browser and retains the local viewer")
                # Preparing a reference is explicit. Merely inspecting a named build never starts a transfer.
                assemblies = page.locator("#igv-reference-assembly")
                for build, alias in (("grch37", "hg19"), ("grch38", "hg38")):
                    assemblies.select_option(build)
                    download = page.get_by_role("button", name=f"Scarica da UCSC {alias}")
                    download.wait_for()
                    check(download.is_visible() and not any(method == "references.download" for method, _ in methods),
                          f"{alias} offers local registration and an explicit download on a fresh installation")
                assemblies.select_option("custom")
                picker.paths = [Path(selection["reference"]["fasta"])]
                page.locator('[data-action="reference-register"][data-scope="igv"]').click()
                probe.wait("!!NipatApp.state.igv.reference.fasta")
                check(page.locator("#igv-registered-fasta").input_value() != "" and
                      probe.evaluate("NipatApp.state.igv.reference.fasta") == selection["reference"]["fasta"],
                      "The registered local genome opens in IGV with the exact selected path")
                page.locator('nav [data-view="new"]').click()
                page.locator("#new-reference-assembly").select_option("custom")
                probe.wait("!!NipatApp.state.draft.reference_id")
                check(probe.evaluate("NipatApp.state.draft.reference") == selection["reference"]["fasta"],
                      "A local FASTA registered in IGV can be selected in a new experiment")
                page.locator('nav [data-view="igv"]').click()
                page.locator("#igv-reference-assembly").select_option("file")
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
                check(probe.evaluate("() => {const root=document.querySelector('#igv-container').shadowRoot;const location=root?.querySelector('.igv-navbar-genomic-location'),zoom=root?.querySelector('[class^=igv-zoom-widget]');return !!location&&!!zoom&&[location,zoom].every(n=>getComputedStyle(n).display==='none')}"), "Duplicate native locus controls are hidden")
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
                probe.wait("!document.querySelector('#toast').classList.contains('visible')&&Number(getComputedStyle(document.querySelector('#toast')).opacity)===0")
                igv = report_path.parent / "igv-alignments.png"
                page.screenshot(path=str(igv), full_page=True)
                evidence["screenshots"].append(igv.name)

                for module, first_value, second_value in (
                        ("cpi", "-3.123456789012345", "0"),
                        ("cpin", "-3.33278849686833", "-3.42969850987639")):
                    page.locator('[data-action="navigate"][data-view="archive"]').click()
                    page.locator(f'[data-action="open-run"][data-id="{module}-curve-ui-fixture"]').click()
                    kind = "prenatal_cpi" if module == "cpi" else "postnatal_cpi"
                    expected = "0,602" if module == "cpi" else "0,00046474155109453"
                    preview = page.locator(f'.outcome-preview[data-outcome="{kind}"]')
                    check(preview.locator("strong").inner_text() == expected,
                          f"{module} overview shows the recorded summary with its original precision")
                    page.locator(f'[role="tab"][data-action="result-module"][data-module="{module}|DNP"]').click()
                    page.wait_for_selector('.interactive-curve .curve-point')
                    panel = page.locator(f'.outcome-panel[data-outcome="{kind}"]')
                    check(panel.locator('[data-outcome-value]').inner_text() == expected,
                          f"{module} selected family shows the same index as the overview")
                    if module == "cpi":
                        check("Tra i limiti" in panel.locator('[data-band="between"]').inner_text(),
                              "Prenatal index uses the archived guides; this family lies between them")
                    else:
                        check(panel.locator("[data-band]").count() == 0,
                              "Postnatal index is displayed without a prenatal threshold")
                    page.get_by_role("radio", name="Italiano", exact=True).press("ArrowRight")
                    value_selector = '.outcome-panel [data-outcome-value]'
                    probe.wait(f"document.querySelector('{value_selector}')?.textContent==='{expected.replace(',', '.')}'")
                    expected_label = ("log₁₀(CPI) at the median fetal read threshold" if module == "cpi"
                                      else "Combined Paternity Index (CPI)")
                    check(panel.locator(".outcome-label").inner_text() == expected_label,
                          f"{module} English summary reloads the same family, metric and numeric result")
                    page.get_by_role("radio", name="English", exact=True).press("ArrowLeft")
                    probe.wait(f"document.querySelector('{value_selector}')?.textContent==='{expected}'")
                    curve_id = probe.evaluate("NipatApp.state.curves[0].file.id")
                    curve_selector = f'.results-body [data-action="curve-mode"][data-id="{curve_id}"]'
                    check(page.locator('.interactive-curve').count() == 2,
                          f"{module.upper()} renders separate CPI and site-count panels from recorded rows")
                    chart = page.locator('.interactive-curve').first
                    tooltip = chart.locator('.curve-tooltip')
                    chart.locator('.curve-hit-dot').first.hover()
                    probe.wait("!document.querySelector('.curve-tooltip').hidden")
                    value_key = "log_CPI" if module == "cpi" else "Log10_CPI"
                    check(tooltip.locator(f'[data-curve-value="{value_key}"]').inner_text() == first_value,
                          f"{module.upper()} mouse hover exposes original precision in an HTML tooltip")
                    chart.locator('.curve-point').first.focus()
                    page.keyboard.press('ArrowRight')
                    check(probe.evaluate("document.activeElement.dataset.curvePoint") == "1",
                          f"{module.upper()} arrow navigation focuses the next recorded point")
                    check(tooltip.locator(f'[data-curve-value="{value_key}"]').inner_text() == second_value,
                          f"{module.upper()} keyboard detail preserves the next original value")
                    page.keyboard.press('Escape')
                    check(tooltip.is_hidden(), f"{module.upper()} Escape dismisses the chart detail")
                    chart.locator('.curve-point').first.focus()
                    if module == "cpin":
                        check("2–5" in tooltip.inner_text(), "CPIN tooltip retains inclusive interval endpoints")
                    check(page.locator('.results-body [data-action="export-file"]').count() > 0,
                          f"{module.upper()} original file exports remain available")
                    page.locator(curve_selector + '[data-mode="combined"]').click()
                    check(page.locator('.interactive-curve').count() == 1,
                          f"{module.upper()} combined view overlays the three recorded series")
                    combined_chart = page.locator('.interactive-curve').first
                    check(combined_chart.locator('.curve-right-label').text_content().strip() == "Conteggi dei siti",
                          f"{module.upper()} combined view explicitly labels its site-count axis")
                    series_keys = probe.evaluate("[...new Set([...document.querySelectorAll('.interactive-curve [data-curve-series]')].map(node=>node.dataset.curveSeries))].sort()")
                    expected_keys = sorted(["log_CPI", "NotMismatch", "Mismatch"] if module == "cpi" else ["Log10_CPI", "Matching_sites", "Mismatching_sites"])
                    check(series_keys == expected_keys, f"{module.upper()} combined view uses exactly the black, green and orange source series")
                    combined_chart.locator('.curve-hit-dot').first.hover()
                    probe.wait("!document.querySelector('.curve-tooltip').hidden")
                    combined_tooltip = combined_chart.locator('.curve-tooltip')
                    check(combined_tooltip.locator(f'[data-curve-value="{value_key}"]').inner_text() == first_value,
                          f"{module.upper()} combined hover preserves the negative original log CPI")
                    combined_chart.locator('.curve-point').first.focus()
                    page.keyboard.press('ArrowRight')
                    check(combined_tooltip.locator(f'[data-curve-value="{value_key}"]').inner_text() == second_value,
                          f"{module.upper()} combined keyboard navigation retains exact values")
                    combined_image = report_path.parent / f"{module}-combined-curve.png"
                    page.screenshot(path=str(combined_image), full_page=True)
                    evidence["screenshots"].append(combined_image.name)
                    page.locator(curve_selector + '[data-mode="separate"]').click()
                    check(page.locator('.interactive-curve').count() == 2,
                          f"{module.upper()} separate views remain available after combined inspection")
                    page.locator('.interactive-curve').first.locator('.curve-point').first.focus()
                    chart_image = report_path.parent / f"{module}-interactive-curve.png"
                    page.screenshot(path=str(chart_image), full_page=True)
                    evidence["screenshots"].append(chart_image.name)

                page.locator('[data-action="navigate"][data-view="archive"]').click()
                page.locator('[data-action="open-run"][data-id="archived-ui-fixture"]').click()
                page.wait_for_selector('[data-action="reuse-run"]')
                page.locator('[role="tab"][data-module="dnp-call|DNP"]').click()
                check(page.locator('.outcome-panel [data-outcome-value]').inner_text() == "Analisi incompleta",
                      "An interrupted call with a partial site table does not appear complete")
                check(page.locator('.result-table .locus-genotype').inner_text() == "0/1",
                      "The recorded heterozygous genotype remains visible at the individual locus")
                page.locator('.page-heading [data-action="run-igv"]').click()
                probe.wait("NipatApp.state.view==='igv'&&NipatApp.state.igv.loaded")
                page.locator('#page-back').click()
                probe.wait("NipatApp.state.view==='archive'&&NipatApp.state.module==='dnp-call|DNP'")
                check(page.locator('#result-marker').input_value() == "dnp-call|DNP",
                      "Page Back from IGV restores the original experiment and marker module")
                page.locator('#page-back').click()
                probe.wait("NipatApp.state.run?.id==='archived-ui-fixture'&&!NipatApp.state.module")
                check(page.locator('.module-card h3').all_text_contents() == ["Conteggi e genotipi DNP"],
                      "Back from a module shows only the recorded caller in the result cards")
                page.locator('[data-action="reuse-run"]').first.click()
                probe.wait("NipatApp.state.view==='new'")
                reused = probe.evaluate("NipatApp.state.draft")
                check(reused["samples"][0]["path"] == selection["tracks"][0]["path"] and reused["reference"] == selection["reference"]["fasta"], "Run again opens original recorded input selections")
                verify_single_start(page, probe, service, methods, check)
                page.locator('[data-action="navigate"][data-view="archive"]').click()
                page.locator('[data-action="remove-run"][data-id="archived-ui-fixture"]').click()
                check('file di input resteranno' in page.locator('[role="dialog"]').inner_text(), "Removal confirmation explains source and result preservation")
                page.locator('[data-action="confirm-remove-run"]').click()
                page.locator('[data-action="open-run"][data-id="archived-ui-fixture"]').wait_for(state="detached")
                check(archived.is_dir() and digest_files(preserved) == before, "Remove from list preserves every source, index, result and metadata byte")
                verify_archive_pages(page, probe, service, methods, check)
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
