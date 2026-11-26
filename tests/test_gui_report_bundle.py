"""A selection from one experiment stays ordered, complete and in a single export."""
import base64
import http.client
import json
from unittest.mock import Mock

import pytest

from nipat.errors import ValidationError
from nipat.gui.analysis_report import report_cases
from nipat.gui.report_bundle import build_bundle, selected_ids
from nipat.gui.results import ResultsStore
from test_gui_app import app
from test_gui_results import make_run, table


def test_bundle_resolves_selection_once_and_keeps_the_same_case_order_in_both_formats(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    table(run / "output/contamination_summary.txt",
          ["individuo", "informative_sites", "mean_contamination"],
          [["first", "3", "0"], ["second", "0", "NA"]])
    store = ResultsStore(tmp_path, language="en")
    ids = [case["id"] for case in reversed(report_cases(store, "example"))]
    calls = Mock(wraps=store.overview)
    monkeypatch.setattr(store, "overview", calls)
    bundle = build_bundle(store, "example", ids, "combined")
    calls.assert_called_once_with("example")
    for name in ("results", "summary_results"):
        assert [row["case_id"] for row in bundle[name]] == ids
        assert [row["outcome_category"] for row in bundle[name]] == ["nonassessable", "descriptive"]
    assert bundle["results"][0]["result_basis"] and "result_basis" not in bundle["summary_results"][0]
    with pytest.raises(ValidationError, match="selection changed"):
        build_bundle(store, "example", [ids[1], "0" * 64], "detailed")


@pytest.mark.parametrize("ids", [[], ["0" * 64] * 2, ["not a case"], None, ["a" * 64, []]])
def test_invalid_selection_is_rejected_before_rendering(ids):
    with pytest.raises(ValidationError):
        selected_ids({"case_ids": ids}, english=True)


def test_large_combined_pdf_streams_through_one_native_dialog(app, tmp_path):
    app.server.start()
    pdf = b"%PDF-1.7\n" + b"x" * (3 * 1024 * 1024) + b"\n%%EOF\n"
    target = tmp_path / "selected.pdf"
    app.host.save_file = Mock(return_value=target)
    metadata = {"selection": "combined", "run_id": "run", "kind": "combined", "language": "en"}
    headers = {"Content-Type": "application/pdf", "Origin": app.server.origin,
               "X-NewPat-Report": base64.b64encode(json.dumps(metadata).encode()).decode()}

    def post(body, update=None):
        client = http.client.HTTPConnection("127.0.0.1", app.server.httpd.server_port, timeout=8)
        try:
            client.request("POST", "/" + app.server.token + "/report-pdf", body, {**headers, **(update or {})})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    assert post(pdf) == (200, {"result": {"path": str(target), "name": target.name}})
    assert target.read_bytes() == pdf
    assert app.host.save_file.call_count == 1
    assert post(b"%PDF-1.7\ntruncated")[0] == 400
    assert post(b"x", {"Origin": "https://example.test"})[0] == 403
    assert post(b"x", {"Content-Type": "text/plain"})[0] == 415
    assert post(b"x", {"X-NewPat-Report": "abc"})[0] == 400
    assert target.read_bytes() == pdf and app.host.save_file.call_count == 1
