"""Additional detail charts built from the selected archived table or curve."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math


def _number(raw, *, count=False):
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    if count:
        # PDF graphs are rendered in JavaScript; do not display a rounded read count.
        if value > 2**53 - 1 or value != value.to_integral_value():
            return None
        return int(value)
    number = float(value)
    return number if math.isfinite(number) and (number != 0 or value == 0) else None


def site_label(row, row_number, en):
    chromosome = row.get("chr")
    first = row.get("pos") or row.get("pos1")
    last = row.get("pos2")
    if (isinstance(chromosome, str) and chromosome and chromosome.isprintable()
            and not any(sep in chromosome for sep in ("/", "\\"))
            and _number(first, count=True) is not None):
        end = f"–{last}" if last is not None and _number(last, count=True) is not None else ""
        return f"{chromosome}:{first}{end}"
    return f"Row {row_number}" if en else f"Riga {row_number}"


def detail_charts(module, table, language):
    """Summarize only the rows actually read for this sample, family and panel."""
    en = language == "en"
    rows = table["rows"]
    if not rows:
        return []
    total = table["total"]
    positions = list(range(len(rows)))
    if module == "cpi":
        # Do not draw a new continuous curve through missing or sampled thresholds.
        if len(positions) > 8:
            positions = [round(i * (len(rows) - 1) / 7) for i in range(8)]
        title = "Paternal sites used at each read threshold" if en else "Siti paterni usati per soglia di letture fetali"
        unit = "Number of contributing sites" if en else "Numero di siti utilizzati"
        explanation = ("The thresholds refer to the selected pair and panel." if en else
                       "Le soglie si riferiscono alla coppia e al pannello selezionati.")
    elif module == "cpin":
        title = "Contribution of individual sites to the CPI" if en else "Contributo dei singoli siti al CPI"
        unit = "Paternity index (PI) per site" if en else "Indice di paternità (PI) per sito"
        explanation = ("Each bar shows the recorded PI for one included site. A value of 1 leaves the combined index unchanged." if en else
                       "Ogni barra mostra il PI registrato per un sito incluso. Un valore pari a 1 lascia invariato l’indice combinato.")
    elif module == "contamination":
        title = "Reads supporting the per-site estimates" if en else "Letture su cui si basano le stime per sito"
        unit = "REF and ALT reads" if en else "Letture REF e ALT"
        explanation = ("The sum of REF and ALT reads is the denominator of each site's contamination estimate." if en else
                       "La somma delle letture REF e ALT è il denominatore della stima di contaminazione di ciascun sito.")
    elif module in {"dnp-call", "snp-call"}:
        title = "Read depth by site" if en else "Copertura di lettura per sito"
        unit = "Read observations" if en else "Osservazioni di lettura"
        explanation = ("Depth is the recorded total for each site. Zero is a measured depth." if en else
                       "La copertura è il totale registrato per ciascun sito. Lo zero indica una copertura misurata.")
    else:
        return []

    points = []
    seen_thresholds = set()
    for i in positions:
        row = rows[i]
        if module == "cpi":
            threshold = _number(row.get("Iteration"), count=True)
            if threshold is None or threshold in seen_thresholds:
                return []
            seen_thresholds.add(threshold)
            label = f"Threshold {threshold}" if en else f"Soglia {threshold}"
            value = _number(row.get("InfSites_father"), count=True)
        else:
            label = site_label(row, i + 1, en)
            if module == "cpin":
                if row.get("Status") != "eligible":
                    continue
                value = _number(row.get("Paternity_Index"))
            elif module == "contamination":
                ref, alt = (_number(row.get(k), count=True) for k in ("N_REF", "N_ALT"))
                value = _number(ref + alt, count=True) if ref is not None and alt is not None else None
            else:
                value = _number(row.get("total_count"), count=True)
        if value is not None:
            points.append({"label": label, "x": i, "y": value})
    if not points:
        return []
    if module == "cpi":
        coverage = (f"Thresholds shown: {len(points)} of {total}." if en else
                    f"Soglie mostrate: {len(points)} su {total}.")
    else:
        coverage = ((f"Table rows examined: the first {len(rows)} of {total}. " if en else
                     f"Righe esaminate: le prime {len(rows)} su {total}. ") if len(rows) < total else "")
        coverage += f"Sites shown: {len(points)} of {total} table rows." if en else f"Siti mostrati: {len(points)} su {total} righe in tabella."
    return [{"title": title, "kind": "bar", "x_label": "", "y_label": unit, "points": points,
             "caption": explanation + " " + coverage}]
