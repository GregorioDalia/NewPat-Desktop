"""Select the platform's embedded native view, never the default browser."""
import sys

from newpat.environment import setting


def native_host():
    if sys.platform == "win32":
        from . import windows_host
        return windows_host
    if sys.platform == "darwin":
        from . import macos_host
        return macos_host
    if sys.platform == "linux":
        from . import linux_host
        return linux_host
    raise RuntimeError("La GUI NewPat supporta Windows, Ubuntu e macOS.")


def smoke_probe_script():
    """Poll native readiness; the full-app qualification also renders a synthetic PDF in memory."""
    verify_pdf = "true" if setting("GUI_VERIFY_PDF") == "1" else "false"
    return """(() => {
        const ready = document.documentElement.dataset.newpatReady === 'true';
        if (VERIFY_PDF && ready && !window.__newpatPdfSmoke) {
            const state = window.__newpatPdfSmoke = {status: 'pending'};
            (async () => {
                const model = {
                    language: 'it', run_name: 'Prova sintetica', subject: 'Campione è',
                    module: 'Genotipi SNP', marker: 'SNP', headline: 'Genotipo assegnato',
                    explanation: 'Prova di leggibilità del PDF', facts: [{label: 'Siti', value: '1'}],
                    metrics: [], notes: [], provenance: []
                };
                const pdf = atob(await window.NewPatReports.render(model, 'summary'));
                if (!pdf.startsWith('%PDF-') || !pdf.trimEnd().endsWith('%%EOF')) {
                    throw new Error('Incomplete PDF');
                }
                state.status = 'passed';
            })().catch(error => { state.status = 'failed'; state.error = String(error); });
        }
        const pdf = window.__newpatPdfSmoke || {};
        return JSON.stringify({appReady: ready, pdfExport: pdf.status, pdfError: pdf.error,
            title: document.title, readyState: document.readyState, userAgent: navigator.userAgent,
            nativeWebView: !!(window.chrome && window.chrome.webview),
            bodyText: document.body.innerText.slice(0, 2000), width: innerWidth, height: innerHeight});
    })()""".replace("VERIFY_PDF", verify_pdf)


def smoke_ready(evidence):
    if evidence.get("pdfExport") == "failed":
        raise RuntimeError("Native PDF export failed: " + str(evidence.get("pdfError", "")))
    return evidence.get("appReady") and evidence.get("pdfExport") != "pending"
