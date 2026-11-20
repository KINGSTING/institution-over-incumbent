"""
Prepare the complete BLGF SRE LGU-level fiscal panel for FY2009–FY2024.

Run from the project root:
    python scripts/prepare_sre_data.py

Requirements:
    python -m pip install openpyxl pandas

Source: data/SRE/
Outputs: outputs/sre_prepared/
Original source workbooks are read only and are never modified.
"""
from pathlib import Path
from collections import Counter
import re
import sys
import traceback

import pandas as pd
from openpyxl import load_workbook

START_YEAR, END_YEAR = 2009, 2024
SOURCE_DIR = Path("data") / "SRE"
OUTPUT_DIR = Path("outputs") / "sre_prepared"

def text(v):
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()

def keytext(v):
    return re.sub(r"[^a-z0-9]+", " ", text(v).casefold()).strip()

def year_from_name(path):
    m = re.search(r"(?:19|20)\d{2}", path.stem)
    return int(m.group()) if m else None

def find_files():
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Cannot find {SOURCE_DIR.resolve()}. Run from the project root "
            "containing the data/SRE folder."
        )
    by_year = {}
    for p in SOURCE_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xlsm"}:
            y = year_from_name(p)
            if y is not None and START_YEAR <= y <= END_YEAR:
                by_year.setdefault(y, []).append(p)
    ambiguous = {y: ps for y, ps in by_year.items() if len(ps) > 1}
    if ambiguous:
        raise RuntimeError("Multiple workbooks found for year(s): " + "; ".join(
            f"{y}: {[p.name for p in ps]}" for y, ps in ambiguous.items()
        ))
    missing = [y for y in range(START_YEAR, END_YEAR + 1) if y not in by_year]
    if missing:
        print("WARNING: missing workbook(s) for:", ", ".join(map(str, missing)))
    return [(y, by_year[y][0]) for y in sorted(by_year)]

def find_header(ws):
    best = None
    for r in range(1, min(ws.max_row, 30) + 1):
        vals = [keytext(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 8) + 1)]
        joined = " | ".join(vals)
        score = sum(s in joined for s in ("region", "province", "lgu name", "lgu type"))
        if score >= 3 and (best is None or score > best[0]):
            best = (score, r)
    return best[1] if best else None

def get_unit(ws):
    parts = []
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 10), values_only=True):
        parts.extend(text(v) for v in row if v is not None)
    title = " ".join(parts).casefold()
    if "php million" in title:
        return "In Php Million (source wording; raw values preserved)"
    if "in peso" in title or "philippine peso" in title:
        return "Peso wording detected; verify exact unit"
    return "Not detected; review source"

def headers_for(ws, header_row, ncols):
    start = max(1, header_row - 5)
    labels = []
    for c in range(1, ncols + 1):
        pieces = []
        for r in range(start, header_row + 1):
            v = text(ws.cell(r, c).value)
            if v and (not pieces or keytext(v) != keytext(pieces[-1])):
                pieces.append(v)
        current = keytext(ws.cell(header_row, c).value)
        if current in {"region", "province", "lgu name", "lgu type"}:
            label = {"region":"region", "province":"province",
                     "lgu name":"lgu_name", "lgu type":"lgu_type"}[current]
        else:
            label = " | ".join(pieces) if pieces else f"source_col_{c:02d}"
        labels.append(re.sub(r"\s+", " ", label).strip(" |"))
    seen, unique = Counter(), []
    for i, label in enumerate(labels, 1):
        label = label or f"source_col_{i:02d}"
        seen[label] += 1
        unique.append(label if seen[label] == 1 else f"{label}__{seen[label]}")
    return unique

def is_lgu(row):
    # Source sheets place Region, Province, LGU Name, LGU Type in Excel columns B:E.
    vals = [row[i] if len(row) > i else None for i in range(1, 5)]
    region, province, name, typ = map(text, vals)
    if not name or not typ:
        return False
    t = keytext(typ)
    if not (t == "province" or "city" in t or "municipal" in t
            or t in {"barangay", "district"}):
        return False
    if keytext(name) in {"lgu name", "total", "grand total", "overall total", "philippines"}:
        return False
    if t == "lgu type":
        return False
    return True

def extract(year, path):
    log = {
        "fiscal_year": year, "source_file": path.name, "status": "ERROR",
        "sheet": "", "header_row": None, "reported_max_row": None,
        "reported_max_column": None, "last_populated_row": None,
        "reported_unit": "", "rows_extracted": 0,
        "duplicate_lgu_keys_in_year": None, "notes": ""
    }
    records, dictionary = [], []
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        candidates = [(ws, find_header(ws)) for ws in wb.worksheets]
        candidates = [(ws, hr) for ws, hr in candidates if hr is not None]
        if not candidates:
            raise ValueError("No header row found for Region/Province/LGU Name/LGU Type.")
        ws, hr = max(candidates, key=lambda pair: pair[0].max_row)
        log.update(status="OK", sheet=ws.title, header_row=hr,
                   reported_max_row=ws.max_row, reported_max_column=ws.max_column,
                   reported_unit=get_unit(ws))

        # Determine actual used row/column, ignoring inflated worksheet dimensions.
        last_row, last_col = 0, 0
        for ri, row in enumerate(ws.iter_rows(max_col=min(ws.max_column, 200), values_only=True), 1):
            nonempty = [i + 1 for i, v in enumerate(row) if v is not None and text(v)]
            if nonempty:
                last_row = ri
                last_col = max(last_col, max(nonempty))
        log["last_populated_row"] = last_row
        if not last_col:
            raise ValueError("No populated cells found.")
        labels = headers_for(ws, hr, last_col)
        for pos, label in enumerate(labels, 1):
            dictionary.append({
                "fiscal_year": year, "source_file": path.name, "source_sheet": ws.title,
                "source_column_position": pos, "prepared_column_name": label,
                "source_header_row": hr, "reported_unit": log["reported_unit"]
            })

        seen = Counter()
        for excel_row, row in enumerate(
            ws.iter_rows(min_row=hr + 1, max_col=last_col, values_only=True), hr + 1
        ):
            if not is_lgu(row):
                continue
            vals = list(row) + [None] * max(0, last_col - len(row))
            rec = {labels[i]: vals[i] for i in range(last_col)}
            rec.update({
                "fiscal_year": year,
                "region": text(vals[1]), "province": text(vals[2]),
                "lgu_name": text(vals[3]), "lgu_type": text(vals[4]),
                "source_file": path.name, "source_sheet": ws.title,
                "source_excel_row": excel_row,
                "reported_unit": log["reported_unit"],
                "source_column_count": last_col
            })
            rec["lgu_key"] = "|".join(keytext(v) for v in
                                      (rec["lgu_type"], rec["province"], rec["lgu_name"]))
            seen[rec["lgu_key"]] += 1
            records.append(rec)
        log["rows_extracted"] = len(records)
        log["duplicate_lgu_keys_in_year"] = sum(n - 1 for n in seen.values() if n > 1)
        if log["duplicate_lgu_keys_in_year"]:
            log["notes"] = "Duplicate provisional LGU keys; inspect before analysis."
        if log["reported_unit"].startswith("Not detected"):
            log["notes"] += (" " if log["notes"] else "") + "Unit wording not detected."
        return records, dictionary, log
    finally:
        wb.close()

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = find_files()
    if not files:
        raise RuntimeError(f"No FY{START_YEAR}–{END_YEAR} workbooks found in {SOURCE_DIR.resolve()}")

    all_records, all_dict, logs = [], [], []
    for year, path in files:
        print(f"[{year}] Reading {path.name} ...")
        try:
            recs, dct, log = extract(year, path)
            all_records.extend(recs)
            all_dict.extend(dct)
            logs.append(log)
            print(f"       {log['status']}: {log['rows_extracted']} LGU records; "
                  f"{log['reported_max_column']} reported columns.")
        except Exception as exc:
            logs.append({
                "fiscal_year": year, "source_file": path.name, "status": "ERROR",
                "sheet": "", "header_row": None, "reported_max_row": None,
                "reported_max_column": None, "last_populated_row": None,
                "reported_unit": "", "rows_extracted": 0,
                "duplicate_lgu_keys_in_year": None,
                "notes": f"{type(exc).__name__}: {exc}"
            })
            print(f"       ERROR: {type(exc).__name__}: {exc}")

    panel = pd.DataFrame(all_records)
    log_df = pd.DataFrame(logs).sort_values("fiscal_year")
    dict_df = pd.DataFrame(all_dict)
    if not panel.empty:
        first = ["fiscal_year", "region", "province", "lgu_name", "lgu_type",
                 "lgu_key", "source_file", "source_sheet", "source_excel_row",
                 "reported_unit", "source_column_count"]
        panel = panel[[c for c in first if c in panel.columns] +
                      [c for c in panel.columns if c not in first]]
        panel = panel.sort_values(
            ["fiscal_year", "region", "province", "lgu_name", "lgu_type"],
            kind="stable"
        ).reset_index(drop=True)

    csv_path = OUTPUT_DIR / "lgu_fiscal_panel_2009_2024.csv"
    xlsx_path = OUTPUT_DIR / "lgu_fiscal_panel_2009_2024.xlsx"
    log_path = OUTPUT_DIR / "extraction_log.csv"
    dict_path = OUTPUT_DIR / "column_dictionary.csv"
    report_path = OUTPUT_DIR / "validation_report.txt"

    panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log_df.to_csv(log_path, index=False, encoding="utf-8-sig")
    dict_df.to_csv(dict_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        panel.to_excel(writer, sheet_name="LGU_Fiscal_Panel", index=False)
        log_df.to_excel(writer, sheet_name="Extraction_Log", index=False)
        dict_df.to_excel(writer, sheet_name="Column_Dictionary", index=False)

    successful = int((log_df["status"] == "OK").sum())
    errors = int((log_df["status"] != "OK").sum())
    report = [
        "BLGF SRE LGU PANEL — EXTRACTION AND VALIDATION REPORT",
        f"Requested years: {START_YEAR}–{END_YEAR}",
        f"Source directory: {SOURCE_DIR.resolve()}",
        f"Output directory: {OUTPUT_DIR.resolve()}",
        "",
        "No unit conversion, inflation adjustment, interpolation, or imputation was applied.",
        "Blank source values remain blank. Historical LGU names/boundaries are not reconciled.",
        "lgu_key is a provisional name/type/province matching key, not an official LGU identifier.",
        "",
        f"Workbooks found: {len(files)}",
        f"Successful workbooks: {successful}",
        f"Workbooks with errors: {errors}",
        f"Total LGU-year records: {len(panel):,}",
        f"Distinct provisional LGU keys: {panel['lgu_key'].nunique() if not panel.empty else 0:,}",
        f"Duplicate provisional keys within years: {int(log_df['duplicate_lgu_keys_in_year'].fillna(0).sum())}",
        "",
        "YEAR-BY-YEAR EXTRACTION:"
    ]
    for _, r in log_df.iterrows():
        report.append(
            f"{int(r['fiscal_year'])}: {r['status']}; rows={int(r['rows_extracted'])}; "
            f"file={r['source_file']}; unit={r['reported_unit']}; notes={r['notes']}"
        )
    report += [
        "",
        "REQUIRED REVIEW BEFORE ANALYSIS:",
        "1. Verify numeric units; the source title and magnitudes may conflict.",
        "2. Review column_dictionary.csv for changing headers/account classifications.",
        "3. Inspect duplicate keys and changes in LGU names/boundaries.",
        "4. Do not interpret missing values as zero.",
        "5. Confirm the extracted row counts against each source workbook."
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")

    print("\nFINISHED. Outputs:")
    for p in [csv_path, xlsx_path, log_path, dict_path, report_path]:
        print(f"  {p.resolve()}")
    if errors:
        print(f"\nWARNING: {errors} workbook(s) failed. Check {log_path} and {report_path}.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
