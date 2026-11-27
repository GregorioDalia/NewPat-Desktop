"""Printable, case-specific views of archived results. No scientific model runs here."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath

from newpat.desktop.report_charts import detail_charts, site_label
from newpat.desktop.results import FIELDS, MISSING, _read_count, _signature, column_description


_PREVIEW_ROWS = 8
_MAX_CURVE_POINTS = 120


def _text(language, it, en):
    return en if language == "en" else it


def _public_label(value):
    # An imported archive can use a host path as a display name. Only its filename
    # belongs on a portable report. Preserve names and the GUI's family separator.
    parts = []
    for label in str(value).split(" / "):
        windows = PureWindowsPath(label)
        if windows.drive or "\\" in label:
            label = windows.name
        elif PurePosixPath(label).is_absolute() or label.startswith(("~/", "../", "./")):
            label = PurePosixPath(label).name
        parts.append(label)
    return " / ".join(parts)


def _display(value, description, language, *, concise=False, guides=None):
    if value == "NA" and "NA" in description.get("values", {}):
        return description["values"]["NA"]
    if value is None or value in MISSING:
        return _text(language, "Non disponibile", "Unavailable")
    if value in description.get("values", {}):
        return description["values"][value]
    if value in ("TRUE", "FALSE"):
        return {"TRUE": _text(language, "Sì", "Yes"), "FALSE": "No"}[value]
    raw = str(value)
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return _public_label(raw)
    if not number.is_finite():
        return raw
    approximate = ""
    if concise and description.get("key") in {
        "CPI", "Log10_CPI", "CPI_medianFF", "Median_fetal_fraction_percent", "mean_contamination",
    }:
        rounded = Decimal(format(number, ".3g"))
        key = description["key"]
        limits = ([Decimal(guides["lower"]), Decimal(guides["upper"])] if guides and key in {"Log10_CPI", "CPI_medianFF"}
                  else [Decimal(1)] if key in {"CPI", "mean_contamination"} else [])
        # Do not make the displayed number cross or coincide with a reference boundary.
        if all((number < limit) == (rounded < limit) and (number > limit) == (rounded > limit) for limit in limits):
            if rounded != number:
                approximate = "≈ "
            number = rounded
            raw = str(number)
    if description.get("scale") == 100:
        # Shift by two decimal places without rounding the recorded significant digits.
        sign, digits, exponent = number.as_tuple()
        raw = str(Decimal((sign, digits, exponent + 2))) if number else "0"
    if language == "it":
        raw = raw.replace(".", ",")
    unit = description.get("unit")
    suffix = f" {unit}" if unit in {"%", "punti %", "percentage points"} else ""
    return approximate + raw + suffix


def _pair(label, value):
    return {"label": label, "value": str(value)}


def _archive_entry(entry, language):
    # The Results view names an entry independently of the report's case selector.
    label = entry.get("label") or entry.get("sample_label") or entry.get("family_id") or _text(language, "Riepilogo", "Overview")
    parts = [_public_label(label)]
    if selection := entry.get("analysis"):
        selection = {"all": "all_compatible_sites", "heterozygous": "heterozygous_child_sites",
                     "other_allele": "heterozygous_child_sites"}.get(selection, selection)
        parts.append(_text(language, "Entrambe le selezioni di siti", "Both site selections") if selection == "both"
                     else _display(selection, column_description("Analysis", language=language), language))
    if cutoff := entry.get("cutoff"):
        parts.append(_public_label(cutoff))
    return " · ".join(parts)


def _result_basis(case, entry, language):
    def t(it, en):
        return _text(language, it, en)

    def quantity(count, one, many):
        return f"{count} {one if count == 1 else many}"

    def sites(count):
        return quantity(count, t("sito", "site"), t("siti", "sites"))

    module = case["module"]
    measures = {m["key"]: m["value"] for m in entry["summary"]["metrics"] if m["available"]}
    if module in {"dnp-call", "snp-call"}:
        method = (t("Per assegnare il genotipo, NewPat conta le coppie di basi osservate insieme su ciascuna lettura del campione.",
                    "To assign a genotype, NewPat counts the pairs of bases observed together on each read from this sample.")
                  if module == "dnp-call" else
                  t("Per assegnare il genotipo, NewPat conta le singole basi osservate nelle letture del campione a ciascuna posizione.",
                    "To assign a genotype, NewPat counts the individual bases observed in the sample’s reads at each position."))
        reads = entry.get("read_observations")
        if reads is None:
            return method + " " + t("Il totale delle osservazioni sui siti non è disponibile.",
                                    "The total number of observations across sites is unavailable.")
        observations = quantity(reads, t("osservazione", "observation"), t("osservazioni", "observations"))
        return t(f"La tabella del campione riporta {observations} in totale, sommando i conteggi dei singoli siti.",
                 f"The sample table records {observations} in total across the individual sites.") + " " + method

    if module == "fetal-sex":
        return t("I conteggi provengono dallo stesso campione di DNA libero circolante materno. "
                 "Confronta la media delle letture non materne nei DNP autosomici e del cromosoma X con la media "
                 "delle letture REF e ALT negli SNP del cromosoma Y. I tre rapporti sono valutati con le soglie registrate.",
                 "The counts come from the same maternal cell-free DNA sample. The analysis compares mean "
                 "non-maternal reads at autosomal and X-chromosome DNPs with mean REF and ALT reads at Y-chromosome "
                 "SNPs. The three ratios are evaluated using the recorded thresholds.")
    if module == "contamination":
        count = _read_count(measures.get("informative_sites"))
        if count is None:
            return t("La tabella del campione non riporta un conteggio utilizzabile dei siti informativi per la stima.",
                     "The sample table has no usable count of informative sites for the estimate.")
        if count == 0:
            return t("Nessun sito del campione soddisfa i criteri per misurare la quota di letture inattese.",
                     "No site in the sample met the criteria for measuring the proportion of unexpected reads.")
        informative = quantity(count, t("sito informativo", "informative site"), t("siti informativi", "informative sites"))
        if "mean_contamination" not in measures:
            return t(f"La tabella riporta {informative} per questo campione. La quota media di letture inattese non è disponibile.",
                     f"The sample table records {informative}. The mean proportion of unexpected reads is unavailable.")
        return t(f"La stima è la media delle percentuali di letture con l’allele inatteso misurate in {informative} del campione. "
                 "Per ciascun sito si considerano le letture dell’allele di riferimento e dell’allele alternativo.",
                 f"The estimate is the mean percentage of reads carrying the unexpected allele across {informative} in this sample. "
                 "At each site, the denominator counts reads carrying either the reference or the alternative allele.")

    if module == "cpi":
        maternal = _read_count(measures.get("N_sites_mother"))
        used = _read_count(measures.get("paternal_used_at_median"))
        candidates = _read_count(measures.get("N_sites_father"))
        pair = (t("Per la coppia e il pannello selezionati", "For the selected pair and panel")
                if entry.get("cutoff") not in (None, *MISSING) else t("Per la coppia selezionata", "For the selected pair"))
        maternal_sites = quantity(maternal, t("sito informativo", "informative site"), t("siti informativi", "informative sites"))
        maternal_basis = (t(f"il riepilogo riporta {maternal_sites} nel campione materno.",
                            f"the summary records {maternal_sites} in the maternal sample.")
                          if maternal is not None else
                          t("il numero di siti informativi materni non è disponibile.", "the maternal informative site count is unavailable."))
        if "Include_homozygous_child" in entry["row"]:
            if used is None:
                return t("La coppia non ha una stima utilizzabile alla soglia mediana di letture fetali.",
                         "The pair has no usable estimate at the median fetal read threshold.")
            het = _read_count(entry["row"].get("N_sites_HET_child"))
            hom = _read_count(entry["row"].get("N_sites_HOM_child"))
            return t(f"Il confronto alla soglia mediana di letture fetali si basa su {sites(used)}. "
                     f"Di questi, {het} rientrano nel gruppo con feto presunto eterozigote (HET) e {hom} "
                     "nel gruppo con feto presunto omozigote (HOM). Ogni sito conteggiato ha un indice di paternità valido.",
                     f"At the median fetal read threshold, {sites(used)} contributed to the pair’s CPI. "
                     f"The counts for the presumed heterozygous (HET) and homozygous (HOM) fetal groups are {het} and {hom}, respectively. "
                     "Each counted site has a valid paternity index.")
        if used is not None:
            paternal_basis = t(f"Alla soglia mediana di letture fetali, il confronto ha utilizzato {sites(used)} del campione paterno.",
                               f"At the median fetal read threshold, the comparison used {sites(used)} from the paternal sample.")
        elif candidates is not None:
            possible = quantity(candidates, t("sito paterno candidato", "paternal candidate site"), t("siti paterni candidati", "paternal candidate sites"))
            paternal_basis = t(f"Il riepilogo riporta {possible}. La tabella non specifica quanti siti abbiano "
                               "contribuito all’indice alla soglia mediana di letture fetali.",
                               f"The summary records {possible}. The table does not specify how many sites "
                               "contributed to the index at the median fetal read threshold.")
        else:
            paternal_basis = t("Il numero di siti paterni utilizzati alla soglia mediana di letture fetali non è registrato.",
                               "The number of paternal sites used at the median fetal read threshold is unrecorded.")
        return f"{pair}, {maternal_basis} {paternal_basis}"

    count = _read_count(measures.get("N_sites"))
    if count is None:
        return t("Il riepilogo del trio non riporta un conteggio utilizzabile dei siti che contribuiscono al confronto.",
                 "The trio summary has no usable count of the sites contributing to the comparison.")
    if count == 0:
        return t("Nessun sito del trio è stato incluso nel calcolo per la selezione indicata.",
                 "No sites from the trio were included in the calculation for this selection.")
    if "CPI" not in measures and "Log10_CPI" not in measures:
        return t(f"Il confronto del trio comprende {sites(count)}. L’indice complessivo non è disponibile.",
                 f"The trio comparison includes {sites(count)}. The combined index is unavailable.")
    return t(f"Per il trio, NewPat ha calcolato l’indice complessivo a partire da {sites(count)}. "
             "Il contributo di ciascun sito deriva dai genotipi osservati e dalle frequenze degli alleli nella popolazione di riferimento.",
             f"NewPat calculated the combined index for this trio from {sites(count)}. "
             "Each site’s contribution uses the observed genotypes and the allele frequencies in the reference population.")


def _cases(store, run_id, *, notes=None):
    overview = store.overview(run_id)
    lang = store.language
    for group in overview["modules"]:
        if group.get("summary_truncated") and notes is not None:
            scope = " · ".join(str(x) for x in (group["label"], group["marker"]) if x)
            notes.append(scope + " — " + _text(lang, "L’elenco mostra fino a 10.000 righe per tabella. "
                                               "Le altre righe sono consultabili nella tabella originale.",
                                               "The list shows up to 10,000 rows per table. "
                                               "Additional rows are available in the original table."))
        files = {item["id"]: item for item in group["files"]}
        for entry in group["entries"]:
            summary = entry["summary"]
            if summary.get("step_status") != "succeeded":
                continue
            source = files[entry["file_id"]]
            row = entry.get("row", {})
            marker = group["marker"] or row.get("Marker_type") or ""
            if row.get("Marker_type") and marker != row["Marker_type"]:
                continue
            family = entry.get("family_id")
            subject = entry.get("sample_label") or entry.get("family_label") or entry.get("label") or source["name"]
            subject = _public_label(subject)
            if family and _public_label(family) != subject:
                subject = f"{_public_label(family)} ({subject})"
            selection = []
            if entry.get("cutoff") not in (None, *MISSING):
                selection.append(_text(lang, "Pannello", "Panel") + " " + _public_label(entry["cutoff"]))
            if entry.get("analysis"):
                selection.append(_display(entry["analysis"], column_description("Analysis", language=lang), lang))
            step_id = source.get("step_id") or entry.get("step_id")
            identity = [run_id, group["module"], marker, step_id, source["id"], entry.get("row_number"),
                        family, entry.get("sample_id"), subject, row, summary.get("guide_band"),
                        [(m["key"], m["value"]) for m in summary["metrics"]]]
            case_id = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            selection = " · ".join(selection)
            label = " · ".join(str(s) for s in (group["label"], marker, subject, selection) if s)
            case = dict(id=case_id, label=label, module=group["module"], marker=marker, subject=subject,
                        selection=selection, step_id=step_id, file_id=source["id"], row_number=entry.get("row_number"))
            yield case, group, entry, source


def report_case_options(store, run_id):
    """List completed result rows. Distinct selections never share a report ID."""
    notes = []
    cases = [case for case, *_ in _cases(store, run_id, notes=notes)]
    repeated = Counter(case["label"] for case in cases)
    for case in cases:
        if repeated[case["label"]] > 1:
            row = case["row_number"]
            suffix = f" · {_text(store.language, 'riga', 'row')} {row + 1}" if row is not None else ""
            case["label"] += f" · {case['step_id']}{suffix} · {case['id'][:12]}"
    return {"cases": cases, "notes": notes}


def report_cases(store, run_id):
    return report_case_options(store, run_id)["cases"]


def _outcome(entry, module, language, *, concise):
    def t(it, en):
        return _text(language, it, en)

    summary = entry["summary"]
    measures = {m["key"]: m for m in summary["metrics"]}
    if module == "fetal-sex":
        call = measures["Fetal_sex"]
        if not call["available"]:
            return "nonassessable", t("Risultato non disponibile", "Result unavailable"), t(
                "Il riepilogo archiviato non contiene una classificazione riconosciuta.",
                "The archived summary contains no recognized classification.")
        if call["value"] == "Undetermined":
            return "inconclusive", t("Sesso fetale indeterminato", "Fetal sex undetermined"), t(
                "I dati del campione non permettono di assegnare il sesso fetale con le soglie utilizzate.",
                "The sample data do not establish fetal sex under the thresholds used.")
        headline = t("Stima del sesso fetale: femminile", "Estimated fetal sex: female") if call["value"] == "F" else t(
            "Stima del sesso fetale: maschile", "Estimated fetal sex: male")
        return "descriptive", headline, t(
            "La stima deriva dai marcatori del DNA libero circolante materno. Le soglie di classificazione sono preliminari.",
            "This estimate uses markers from maternal cell-free DNA. The classification thresholds are preliminary.")
    primary = {"cpi": "CPI_medianFF", "cpin": "CPI", "contamination": "mean_contamination"}.get(module, "assigned")
    if module == "cpin" and not measures[primary]["available"] and measures["Log10_CPI"]["available"]:
        primary = "Log10_CPI"
    selected = measures[primary]
    valid = selected["available"]
    value = _display(selected["value"], selected, language, concise=concise, guides=summary.get("guide_band"))
    if not valid:
        supports = {"cpi": ("N_sites_mother", "N_sites_father"), "cpin": ("N_sites",),
                    "contamination": ("informative_sites",)}.get(module, ())
        if any(_number(measures[k]["value"]) == 0 for k in supports):
            return "nonassessable", t("Risultato non disponibile", "Result unavailable"), t(
                "Il numero di siti utilizzabili è insufficiente per questo confronto.",
                "There are insufficient usable sites for this analysis.")
        return "nonassessable", t("Risultato non disponibile", "Result unavailable"), t(
            "I dati registrati per questa analisi non permettono di riportare una stima utilizzabile.",
            "The data recorded for this analysis do not provide a usable estimate.")
    if primary == "assigned":
        total = measures["site_count"]["value"]
        return "descriptive", t(f"Genotipo determinato in {value} siti su {total}", f"Genotype determined at {value} of {total} sites"), t(
            "Il genotipo descrive la combinazione di alleli osservata nel campione in una posizione del DNA.",
            "The genotype describes the combination of alleles observed in the sample at a position in its DNA.")
    if primary == "mean_contamination":
        return "descriptive", t(f"Contaminazione media stimata: {value}", f"Estimated mean contamination: {value}"), t(
            "La stima si basa sulle letture inattese nei siti informativi del campione.",
            "The estimate uses unexpected reads at informative sites in this sample.")
    band = summary.get("guide_band")
    if not band:
        return "nonassessable", t("Conclusione sulla paternità non disponibile", "Paternity conclusion unavailable"), t(
            "NewPat ha calcolato un indice per questi campioni. Il risultato archiviato non fornisce i dati necessari per classificarlo.",
            "NewPat calculated an index for these samples. The archived result lacks the information needed to classify it.")
    position = band["position"]
    log_value = Decimal(measures["CPI_medianFF" if module == "cpi" else "Log10_CPI"]["value"])
    inconclusive = t("Esito inconcludente", "Inconclusive result")
    plain_inconclusive = t("Per i campioni analizzati, il confronto del DNA non permette di confermare o escludere "
                        "che l’uomo esaminato sia il padre.",
                        "For these samples, the DNA comparison does not establish or rule out that the tested man is the father.")
    # Prenatal reference lines are plot guides. Even outside them, the sign of
    # the likelihood ratio can describe relative evidence, never prove parentage.
    if position in {"at_lower", "at_upper"}:
        category, title = "inconclusive", inconclusive
        if concise:
            explanation = plain_inconclusive
        elif module == "cpi":
            explanation = t("Il valore prenatale arrotondato coincide con un limite del grafico. "
                            "Da questo valore non si può stabilire una conclusione sulla paternità.",
                            "The rounded prenatal value falls on a plot boundary. "
                            "This value does not settle the question of paternity.")
        else:
            explanation = t("Il risultato coincide con un limite della fascia inconcludente di questa analisi. "
                            "Il confronto non permette di confermare o escludere la paternità.",
                            "The result falls on the boundary of the inconclusive range for this analysis. "
                            "It neither establishes nor excludes paternity.")
    elif position == "between":
        category, title = "inconclusive", inconclusive
        explanation = plain_inconclusive
    elif position == "above" and log_value > 0:
        category, title = "favorable", t("Il confronto favorisce l’ipotesi di paternità", "The comparison favors paternity")
        explanation = t("I dati genetici osservati sono più probabili se l’uomo esaminato è il padre che se il padre "
                        "è un altro uomo non imparentato.", "The genetic findings are more likely if the tested man "
                        "is the father than if another, unrelated man is the father.")
    elif position == "below" and log_value < 0:
        category, title = "unfavorable", t("Il confronto sfavorisce l’ipotesi di paternità", "The comparison weighs against paternity")
        explanation = t("I dati genetici osservati sono più probabili se il padre è un altro uomo non imparentato "
                        "che se l’uomo esaminato è il padre.", "The genetic findings are more likely if another, "
                        "unrelated man is the father than if the tested man is the father.")
    else:
        # Valid user-defined guides may lie on the same side of zero. A
        # negative log index can never favor paternity merely because it lies
        # above a negative upper guide (and conversely for a positive one).
        category, title = "inconclusive", inconclusive
        explanation = plain_inconclusive if concise else t("Con i limiti scelti per questa analisi, il confronto non consente una conclusione sulla paternità.",
                        "With the limits chosen for this analysis, the comparison does not settle the question of paternity.")
    if not concise:
        low = _display(band["lower"], {}, language)
        high = _display(band["upper"], {}, language)
        guidance = (t("Guide grafiche prenatali", "Prenatal plot guides") if module == "cpi" else
                    t("Limiti del confronto postnatale", "Postnatal comparison limits"))
        explanation += f" {guidance} (log₁₀): {low}, {high}."
    return category, title, explanation


def _number(value):
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _chart(title, kind, x_label, y_label, data):
    return {"title": title, "kind": kind, "x_label": x_label, "y_label": y_label,
            "points": [{"label": str(label), "x": x, "y": y} for label, x, y in data]} if data else None


def _detail_table(store, run_id, file_id, *, curve=False):
    path, descriptor = store._file(run_id, file_id)
    snapshot = _signature(path)
    digest = descriptor.get("recorded_sha256")
    if digest:
        store.verify_count_table(path, digest)
    table = store.curve(run_id, file_id) if curve else store.table(run_id, file_id, limit=_PREVIEW_ROWS)
    if _signature(path) != snapshot:
        raise ValueError("The archived report source changed while reading.")
    return table


def _prenatal_components(store, run_id, entry, result):
    """Read the two recorded contributions at the reported median threshold and its panel-specific site table."""
    row = entry["row"]
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)
    points = [(category, i, _number(row.get(f"Log10_CPI_{category}_child")))
              for i, category in enumerate(("HET", "HOM"))]
    if _number(row.get("CPI_medianFF")) is not None and all(value is not None for _, _, value in points):
        chart = _chart(t("Contributi al CPI alla soglia mediana", "CPI contributions at the median threshold"),
                       "bar", "", "log₁₀(CPI)", points)
        chart["caption"] = t("HET indica i siti con feto presunto eterozigote. HOM indica quelli con feto presunto omozigote. "
                             "Quando attivo, il contributo HOM è costante a tutte le soglie.",
                             "HET denotes presumed heterozygous fetal sites. HOM denotes presumed homozygous fetal sites. "
                             "When enabled, the HOM contribution is constant across thresholds.")
        result.setdefault("charts", []).append(chart)
    if row.get("Include_homozygous_child") != "TRUE":
        return
    result["notes"].append(t("L’analisi comprende la modalità sperimentale per i siti con feto presunto omozigote.",
                             "The analysis used the experimental option for presumed homozygous fetal sites."))
    if not entry.get("site_file_id"):
        result["notes"].append(t("Tabella dei siti HOM non disponibile per la coppia e il pannello selezionati.",
                                 "HOM site table unavailable for the selected pair and panel."))
        return
    table = _detail_table(store, run_id, entry["site_file_id"])
    columns = {col["key"]: col for col in table["columns"]}
    keys = [key for key in ("chr", "pos", "pos1", "pos2", "Paternal_allele", "Paternity_Index") if key in columns]
    if "Paternity_Index" not in keys:
        raise ValueError("Missing site PI.")
    result["tables"] = [result["table"]] if result["table"] else []
    result["tables"].append({
        "title": table["file"]["label"], "columns": [columns[k]["label"] for k in keys],
        "rows": [[_display(row[k], columns[k], lang) for k in keys] for row in table["rows"]],
        "note": t(f"Righe mostrate: {len(table['rows'])} di {table['total']}.",
                  f"Rows shown: {len(table['rows'])} of {table['total']}.")})


def _details(store, run_id, case, entry, result):
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)

    module = case["module"]
    overview_metrics = {m["key"]: m for m in entry["summary"]["metrics"]}
    if module == "fetal-sex":
        points = []
        for i, (key, label) in enumerate((("MFF_A", t("Autosomi", "Autosomes")), ("MFF_X", "X"), ("MFF_Y", "Y"))):
            value = _number(overview_metrics[key]["value"])
            if value is not None:
                points.append((label, i, value))
        result["chart"] = _chart(t("Letture medie per sito", "Mean reads per site"), "bar", "",
                                 t("Letture", "Reads"), points)
        if result["chart"]:
            result["chart"]["caption"] = t(
                "Sugli autosomi e su X si contano le letture non materne. Su Y si contano le letture REF e ALT.",
                "Autosomal and X counts include non-maternal reads. Y counts include REF and ALT reads.")
        result["tables"] = []
        keys_by_file = {"Autosomal_informative_sites.txt": ("chr", "pos1", "pos2", "fetal_reads"),
                        "X_informative_sites.txt": ("chr", "pos1", "pos2", "fetal_reads"),
                        "Y_sites.txt": ("chr", "pos", "Y_reads", "Included")}
        for name, keys in keys_by_file.items():
            file_id = entry["site_tables"].get(name)
            if not file_id:
                result["notes"].append(t("Tabella dei siti non disponibile", "Site table unavailable") + f" ({name}).")
                continue
            table = _detail_table(store, run_id, file_id)
            columns = {col["key"]: col for col in table["columns"]}
            if not all(key in columns for key in keys):
                raise ValueError("Missing site columns.")
            result["tables"].append({
                "title": table["file"]["label"],
                "columns": [columns[k]["label"] for k in keys],
                "rows": [[_display(row[k], columns[k], lang) for k in keys] for row in table["rows"]],
                "note": t(f"Righe mostrate: {len(table['rows'])} di {table['total']}.",
                          f"Rows shown: {len(table['rows'])} of {table['total']}.")})
        return
    count_keys = (("hom_ref", "heterozygous", "hom_alt", "unassigned") if module in {"dnp-call", "snp-call"} else
                  ("Matching_sites", "Mismatching_sites", "No_obligatory_allele_sites") if module == "cpin" else ())
    if count_keys:
        counts = [overview_metrics[k] for k in count_keys if k in overview_metrics]
        if counts and all(_number(m["value"]) is not None for m in counts):
            title = t("Genotipi osservati", "Observed genotypes") if module.endswith("-call") else t("Confronto dei siti paterni", "Paternal site comparison")
            result["chart"] = _chart(title, "bar", "", t("Numero di siti", "Site count"),
                                     [(m["label"], i, _number(m["value"])) for i, m in enumerate(counts)])
    if module == "cpin" and entry.get("analysis"):
        # A legacy sites file can cover more than the selection printed above.
        # Use the selection-specific native intervals, without plotting a new curve.
        if len(entry.get("curve_file_ids", [])) != 1:
            return
        table = _detail_table(store, run_id, entry["curve_file_ids"][0], curve=True)
        keys = ("Min_child_reads", "Through_min_child_reads", "Log10_CPI", "N_sites")
    elif module == "cpi" and len(entry.get("curve_file_ids", [])) == 1:
        curve = _detail_table(store, run_id, entry["curve_file_ids"][0], curve=True)
        rows = curve["rows"]
        points = [(r.get("Iteration"), _number(r.get("Iteration")), _number(r.get("log_CPI"))) for r in rows]
        # Connecting points across an unavailable threshold would invent a curve segment.
        if points and all(x is not None and y is not None for label, x, y in points) and all(
                b[1] - a[1] == 1 for a, b in zip(points, points[1:])):
            if len(points) > _MAX_CURVE_POINTS:
                # Preserve the native endpoints and disclose the sampling of a dense curve.
                last = len(points) - 1
                points = [points[round(i * last / (_MAX_CURVE_POINTS - 1))] for i in range(_MAX_CURVE_POINTS)]
                result["notes"].append(t(f"Il grafico mostra {len(points)} delle {len(rows)} soglie registrate, inclusi gli estremi.",
                                         f"The chart shows {len(points)} of the {len(rows)} recorded thresholds, including both endpoints."))
            result["chart"] = _chart(t("Indice per soglia di letture fetali", "Index by fetal read threshold"), "line",
                                     t("Letture fetali minime", "Minimum fetal reads"), "log₁₀(CPI)", points)
        elif points:
            result["notes"].append(t("La curva contiene soglie o valori non utilizzabili. Consulta la tabella originale.",
                                     "The curve contains unavailable thresholds or values. See the original table."))
        table = curve
        keys = (("Iteration", "log_CPI", "N_sites_HET_child", "N_sites_HOM_child")
                if "Include_homozygous_child" in entry["row"] else
                ("Iteration", "log_CPI", "InfSites_mother", "InfSites_father"))
    else:
        if module == "cpi":
            return
        file_id = entry.get("site_file_id") if not module.endswith("-call") else entry["file_id"]
        if not file_id:
            return
        table = _detail_table(store, run_id, file_id)
        keys = ("chr", "pos1", "pos2", "pos", "GT", "total_count") if module.endswith("-call") else (
            ("chr", "pos1", "pos2", "pos", "contamination") if module == "contamination" else
            ("chr", "pos1", "pos2", "pos", "Status", "Paternity_Index"))
    columns = {c["key"]: c for c in table["columns"]}
    keys = [key for key in keys if key in columns]
    rows = table["rows"][:_PREVIEW_ROWS]
    if not keys or not rows:
        return
    title = (t("Soglie della curva", "Curve thresholds") if "Iteration" in keys else
             t("Intervalli di lettura archiviati", "Archived read intervals") if "Through_min_child_reads" in keys else
             t("Dettaglio dei siti", "Site details"))
    result["table"] = {"title": title, "columns": [columns[k]["label"] for k in keys],
                       "rows": [[_display(row.get(k), columns[k], lang) for k in keys] for row in rows],
                       "note": t(f"Righe mostrate: {len(rows)} di {table['total']}.", f"Rows shown: {len(rows)} of {table['total']}.")}
    if module == "contamination" and "contamination" in keys:
        points = []
        for i, row in enumerate(rows):
            value = _number(row.get("contamination"))
            if value is not None and 0 <= value <= 1:
                points.append((site_label(row, i + 1, lang == "en"), i, value * 100))
        result["chart"] = _chart(t("Contaminazione nei siti mostrati", "Contamination at the sites shown"), "bar", "", "%", points)
    result["charts"] = detail_charts(module, table, lang, legacy_selection=bool(entry.get("analysis")))


def build_report(store, run_id, case_id, *, detailed=False):
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)

    selected = next((row for row in _cases(store, run_id) if row[0]["id"] == case_id), None)
    if selected is None:
        raise ValueError(t("Seleziona un risultato completato. Aggiorna l’elenco se l’esperimento è cambiato.",
                           "Select a completed result. Refresh the list if the experiment has changed."))
    return _build_selected_report(store, run_id, selected, store.get_run(run_id), detailed=detailed)


def _build_selected_report(store, run_id, selected, record, *, detailed):
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)

    case, group, entry, _ = selected
    case_id = case["id"]
    step_id = case["step_id"]
    if not any(s["id"] == step_id and s["status"] == "succeeded" for s in record["steps"]):
        raise ValueError(t("La fase selezionata non è completata.", "The selected step has not completed."))
    metrics = {m["key"]: _pair(m["label"], _display(m["value"], m, lang, concise=not detailed,
                                                   guides=entry["summary"].get("guide_band")))
               for m in entry["summary"]["metrics"]}
    for metric in entry["metrics"]:
        if metric["key"] not in metrics:
            metrics[metric["key"]] = _pair(metric["label"], _display(metric["value"], metric, lang))
    facts = {"fetal-sex": ("N_A_sites", "N_X_sites", "N_Y_sites_used"),
             "cpi": ("CPI_medianFF", "paternal_used_at_median", "Median_fetal_fraction_percent"),
             "cpin": ("CPI", "Log10_CPI", "N_sites"), "contamination": ("mean_contamination", "informative_sites"),
             "dnp-call": ("assigned", "site_count", "unassigned"), "snp-call": ("assigned", "site_count", "unassigned")}
    if not detailed and case["module"] in {"cpi", "cpin"}:
        facts["cpi"] = ("paternal_used_at_median",)
        facts["cpin"] = ("N_sites",)
        for key in facts[case["module"]]:
            if key in metrics:
                metrics[key] = _pair(t("Posizioni del DNA confrontate", "DNA positions compared"), metrics[key]["value"])
    category, headline, explanation = _outcome(entry, case["module"], lang, concise=not detailed)
    if record["status"] != "succeeded":
        explanation += t(" La fase selezionata è completata; l’esperimento nel suo insieme non risulta completato.",
                         " The selected step completed; the overall experiment is not recorded as completed.")
    result = {"language": lang, "case_id": case_id, "run_id": run_id, "run_name": _public_label(record["name"]), "date": record.get("finished_at") or "",
              "version": record.get("version") or "", "workflow": case["module"], "module": group["label"], "marker": case["marker"],
              "subject": case["subject"], "selection": case["selection"], "outcome_category": category, "headline": headline, "explanation": explanation,
              "facts": [metrics[k] for k in facts[case["module"]] if k in metrics], "metrics": [], "chart": None,
              "table": None, "notes": []}
    family = next((f for f in record["families"] if f["id"] == entry.get("family_id") and f["step_id"] == step_id
                   and f["native_id"] == entry.get("native_family")), None)
    result["subjects"] = []
    if family:
        labels = {sample["id"]: sample["label"] for sample in record["samples"]}
        for role, it, en in (("mother", "Campione materno", "Maternal sample"),
                             ("father", "Presunto padre", "Alleged father"), ("child", "Figlio", "Child")):
            sample_id = family.get(role)
            if sample_id:
                label = _public_label(labels.get(sample_id, sample_id))
                identifier = _public_label(sample_id)
                result["subjects"].append(_pair(t(it, en), identifier if identifier == label else f"{identifier} · {label}"))
    if result["subjects"]:
        result["subject"] = _public_label(entry["family_id"])
    elif entry.get("native_family") and _public_label(entry["native_family"]) != result["subject"]:
        result["subjects"] = [_pair(t("Identificativo nella tabella", "Identifier in the source table"),
                                    _public_label(entry["native_family"]))]
    if not detailed:
        return result
    result["result_basis"] = _result_basis(case, entry, lang)
    result["archive_entry"] = _archive_entry(entry, lang)
    for k, value in entry.get("row", {}).items():
        if k in FIELDS and k not in metrics and k not in {"Trio", "Pair", "Analysis", "Cutoff", "Marker_type", "individuo"}:
            column = column_description(k, language=lang, headers=entry["row"])
            metrics[k] = _pair(column["label"], _display(value, column, lang))
    result["metrics"] = list(metrics.values())
    if group["warnings"] or any(w.get("step_id") in (None, "", step_id) for w in record["warnings"]):
        result["notes"].append(t("L’esperimento contiene avvisi. Consulta i dettagli della fase in NewPat.",
                                 "The experiment contains warnings. Review the step details in NewPat."))
    try:
        _details(store, run_id, case, entry, result)
        if case["module"] == "cpi" and "Include_homozygous_child" in entry["row"]:
            _prenatal_components(store, run_id, entry, result)
    except (OSError, ValueError):
        result["notes"].append(t("Il dettaglio per sito o per soglia non è disponibile nell’archivio.",
                                 "Site or threshold details are unavailable in the archive."))
    result["charts"] = ([result["chart"]] if result["chart"] else []) + result.get("charts", [])
    return result
