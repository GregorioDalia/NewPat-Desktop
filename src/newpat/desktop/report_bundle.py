"""Resolve one experiment's selected results once for a single PDF export."""
import re

from newpat.errors import ValidationError
from .analysis_report import _build_selected_report, _cases


def selected_ids(params, english):
    ids = params.get("case_ids")
    if "case_ids" not in params and "case_id" in params:
        ids = [params["case_id"]]
    if (not isinstance(ids, list) or not ids or
            any(not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{64}", identifier)
                for identifier in ids) or len(set(ids)) != len(ids)):
        raise ValidationError("Select one or more distinct results." if english else
                              "Seleziona uno o più risultati distinti.")
    return ids


def build_bundle(store, run_id, ids, kind):
    wanted = set(ids)
    matches = {}
    for row in _cases(store, run_id):
        identifier = row[0]["id"]
        if identifier in wanted:
            matches[identifier] = row
            if len(matches) == len(wanted):
                break
    if len(matches) != len(ids):
        raise ValidationError("The selection changed. Reopen the list of results." if store.language == "en" else
                              "La selezione è cambiata. Riapri l’elenco dei risultati.")
    record = store.get_run(run_id)

    def models(detailed):
        return [_build_selected_report(store, run_id, matches[identifier], record, detailed=detailed)
                for identifier in ids]

    results = models(kind != "summary")
    bundle = {key: results[0][key] for key in ("language", "run_id", "run_name", "date", "version")}
    bundle["results"] = results
    if kind == "combined":
        bundle["summary_results"] = models(False)
    return bundle
