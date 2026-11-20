#!/usr/bin/env python
"""
Consolidated, read-only audit of the prepared BLGF SRE panel.

Run from the project root:
    python scripts/02_audit_sre_data.py

Expected inputs:
    outputs/sre_prepared/lgu_fiscal_panel_2009_2024.csv
    outputs/sre_prepared/column_dictionary.csv
    outputs/sre_prepared/extraction_log.csv
    data/SRE/*.xlsx (optional but recommended for workbook dimension checks)

Writes audit outputs to outputs/sre_audit/.
Does not modify source workbooks or prepared inputs. Does not convert units,
impute values, or delete records.
"""
from pathlib import Path
import re
import sys
import math
import warnings
import pandas as pd
import numpy as np

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

START_YEAR, END_YEAR = 2009, 2024
EXPECTED_YEARS = list(range(START_YEAR, END_YEAR + 1))
TOLERANCE = 1.0  # reported only; no values are changed

def find_project_root():
    here = Path.cwd()
    if (here / "outputs" / "sre_prepared").exists() or (here / "data" / "SRE").exists():
        return here
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir, *script_dir.parents]:
        if (candidate / "outputs" / "sre_prepared").exists() or (candidate / "data" / "SRE").exists():
            return candidate
    return here

def safe_read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    # Keep IDs/names as text where possible; pandas still infers numeric fiscal columns.
    return pd.read_csv(path, low_memory=False)

def norm_text(value):
    if pd.isna(value):
        return ""
    s = str(value).strip().casefold()
    s = s.replace("&", " and ")
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()

def write_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")

def describe_numeric(panel, metadata_cols):
    rows = []
    for col in panel.columns:
        if col in metadata_cols:
            continue
        s = pd.to_numeric(panel[col], errors="coerce")
        observed = s.dropna()
        if len(observed) == 0:
            continue
        rows.append({
            "variable": col,
            "nonmissing_n": int(observed.size),
            "missing_n": int(s.isna().sum()),
            "missing_pct": round(float(s.isna().mean() * 100), 3),
            "min": observed.min(),
            "p01": observed.quantile(.01),
            "median": observed.median(),
            "p99": observed.quantile(.99),
            "max": observed.max(),
            "negative_n": int((observed < 0).sum()),
            "zero_n": int((observed == 0).sum()),
            "integer_like_pct": round(float(np.isclose(observed % 1, 0).mean() * 100), 2),
        })
    return pd.DataFrame(rows)

def workbook_dimensions(root, log):
    rows = []
    source_dir = root / "data" / "SRE"
    if not source_dir.exists():
        return pd.DataFrame([{"status": "SOURCE_DIR_NOT_FOUND", "path": str(source_dir)}])
    if load_workbook is None:
        return pd.DataFrame([{"status": "OPENPYXL_NOT_INSTALLED", "path": str(source_dir)}])
    for year in EXPECTED_YEARS:
        matches = [p for p in source_dir.rglob("*") if p.is_file()
                   and p.suffix.lower() in (".xlsx", ".xlsm")
                   and re.search(rf"(?<!\d){year}(?!\d)", p.name)]
        if not matches:
            rows.append({"fiscal_year": year, "status": "WORKBOOK_NOT_FOUND"})
            continue
        for path in matches:
            try:
                wb = load_workbook(path, read_only=True, data_only=True)
                ws = wb[wb.sheetnames[0]]
                # Check actual nonempty cells within a bounded scan. The 2023 used-range
                # can be inflated to XFD; never iterate all 16,384 columns.
                scan_max_col = min(max(ws.max_column or 1, 1), 100)
                last_nonempty_row = 0
                last_nonempty_col = 0
                nonempty_cells = 0
                for r_idx, row in enumerate(ws.iter_rows(
                        min_row=1, max_row=ws.max_row or 1,
                        min_col=1, max_col=scan_max_col, values_only=True), start=1):
                    row_has_data = False
                    for c_idx, value in enumerate(row, start=1):
                        if value is not None and str(value).strip() != "":
                            nonempty_cells += 1
                            row_has_data = True
                            last_nonempty_col = max(last_nonempty_col, c_idx)
                    if row_has_data:
                        last_nonempty_row = r_idx
                rows.append({
                    "fiscal_year": year, "status": "OK", "file": str(path.relative_to(root)),
                    "sheet_checked": ws.title, "reported_max_row": ws.max_row,
                    "reported_max_column": ws.max_column, "scan_column_cap": scan_max_col,
                    "last_nonempty_row_within_scan": last_nonempty_row,
                    "last_nonempty_column_within_scan": last_nonempty_col,
                    "nonempty_cells_within_scan": nonempty_cells,
                    "inflated_column_dimension_flag": bool((ws.max_column or 0) > 100),
                    "note": "bounded scan through first 100 columns; no workbook edits",
                })
                wb.close()
            except Exception as exc:
                rows.append({"fiscal_year": year, "status": "ERROR", "file": str(path),
                             "error": repr(exc)})
    return pd.DataFrame(rows)

def main():
    root = find_project_root()
    prepared = root / "outputs" / "sre_prepared"
    panel_path = prepared / "lgu_fiscal_panel_2009_2024.csv"
    dict_path = prepared / "column_dictionary.csv"
    log_path = prepared / "extraction_log.csv"
    out = root / "outputs" / "sre_audit"
    out.mkdir(parents=True, exist_ok=True)

    panel = safe_read_csv(panel_path)
    dictionary = safe_read_csv(dict_path)
    log = safe_read_csv(log_path)

    required = {"fiscal_year", "region", "province", "lgu_name", "lgu_type", "lgu_key"}
    missing_required = sorted(required - set(panel.columns))
    if missing_required:
        raise ValueError(f"Panel is missing required columns: {missing_required}")
    panel["fiscal_year"] = pd.to_numeric(panel["fiscal_year"], errors="coerce").astype("Int64")
    for col in ["region", "province", "lgu_name", "lgu_type", "lgu_key"]:
        panel[col] = panel[col].astype("string").str.strip()

    # 1) Basic panel, duplicate and missingness checks
    year_counts = panel.groupby("fiscal_year", dropna=False).size().rename("panel_rows").reset_index()
    expected = pd.DataFrame({"fiscal_year": EXPECTED_YEARS})
    year_counts = expected.merge(year_counts, on="fiscal_year", how="left")
    year_counts["panel_rows"] = year_counts["panel_rows"].fillna(0).astype(int)
    year_counts["expected_vs_median_difference"] = year_counts["panel_rows"] - int(year_counts.loc[year_counts.fiscal_year.ne(2013) & year_counts.fiscal_year.ne(2020), "panel_rows"].median())
    if "rows_extracted" in log.columns:
        year_counts = year_counts.merge(log[["fiscal_year", "rows_extracted", "reported_max_row",
                                             "reported_max_column", "last_populated_row", "status"]],
                                        on="fiscal_year", how="left")
        year_counts["panel_vs_extraction_log_diff"] = year_counts["panel_rows"] - pd.to_numeric(year_counts["rows_extracted"], errors="coerce").fillna(0)
    write_csv(year_counts, out / "01_year_counts.csv")

    dup = panel[panel.duplicated(["fiscal_year", "lgu_key"], keep=False)].sort_values(["fiscal_year", "lgu_key"])
    write_csv(dup, out / "02_duplicate_lgu_year_keys.csv")
    missingness = pd.DataFrame({
        "column": panel.columns,
        "dtype": [str(panel[c].dtype) for c in panel.columns],
        "missing_n": [int(panel[c].isna().sum()) for c in panel.columns],
        "missing_pct": [round(float(panel[c].isna().mean()*100), 3) for c in panel.columns],
        "distinct_nonmissing": [int(panel[c].nunique(dropna=True)) for c in panel.columns],
    }).sort_values(["missing_pct", "column"], ascending=[False, True])
    write_csv(missingness, out / "03_missingness_by_column.csv")

    # 2) Numeric magnitudes, without unit conversion
    metadata = {"fiscal_year", "region", "province", "lgu_name", "lgu_type", "lgu_key",
                "source_file", "source_sheet", "source_excel_row", "reported_unit",
                "source_column_count"}
    numeric_summary = describe_numeric(panel, metadata)
    write_csv(numeric_summary, out / "04_numeric_magnitude_summary.csv")

    # Year-wise distribution for each fiscal variable, useful for spotting scale breaks
    scale_rows = []
    for col in panel.columns:
        if col in metadata:
            continue
        s = pd.to_numeric(panel[col], errors="coerce")
        if s.notna().sum() == 0:
            continue
        for year, group in panel.groupby("fiscal_year"):
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            scale_rows.append({
                "fiscal_year": int(year), "variable": col, "n": int(vals.size),
                "missing_n": int(group.shape[0] - vals.size),
                "min": vals.min() if len(vals) else np.nan,
                "median": vals.median() if len(vals) else np.nan,
                "p95": vals.quantile(.95) if len(vals) else np.nan,
                "max": vals.max() if len(vals) else np.nan,
                "negative_n": int((vals < 0).sum()) if len(vals) else 0,
            })
    scale_df = pd.DataFrame(scale_rows)
    if not scale_df.empty:
        scale_df["median_ratio_to_previous_year"] = scale_df.groupby("variable")["median"].transform(lambda s: s / s.shift(1).replace(0, np.nan))
    write_csv(scale_df, out / "05_numeric_by_year.csv")

    # 3) Dictionary audit: columns appearing/disappearing, labels and positions changing
    if "fiscal_year" in dictionary.columns:
        dictionary["fiscal_year"] = pd.to_numeric(dictionary["fiscal_year"], errors="coerce").astype("Int64")
    label_col = "prepared_column_name" if "prepared_column_name" in dictionary.columns else None
    position_col = "source_column_position" if "source_column_position" in dictionary.columns else None
    if label_col:
        dictionary[label_col] = dictionary[label_col].astype("string").str.strip()
        dict_rows = []
        for _, r in dictionary.iterrows():
            label = str(r[label_col]) if pd.notna(r[label_col]) else ""
            dict_rows.append({
                "fiscal_year": int(r["fiscal_year"]) if pd.notna(r.get("fiscal_year")) else None,
                "prepared_column_name": label,
                "normalized_label": norm_text(label),
                "source_column_position": r.get(position_col, np.nan),
                "source_file": r.get("source_file", r.get("source_file", "")),
                "source_header_row": r.get("source_header_row", np.nan),
            })
        dlong = pd.DataFrame(dict_rows)
        # Per normalized label, list years seen and positions seen
        presence = []
        for norm, g in dlong.groupby("normalized_label", dropna=False):
            presence.append({
                "normalized_label": norm,
                "labels_as_recorded": " | ".join(sorted(set(g["prepared_column_name"].dropna().astype(str)))),
                "years_present": ";".join(map(str, sorted(set(g["fiscal_year"].dropna().astype(int))))),
                "year_count": int(g["fiscal_year"].nunique()),
                "first_year": int(g["fiscal_year"].min()) if g["fiscal_year"].notna().any() else None,
                "last_year": int(g["fiscal_year"].max()) if g["fiscal_year"].notna().any() else None,
                "positions": ";".join(map(str, sorted(set(pd.to_numeric(g["source_column_position"], errors="coerce").dropna().astype(int))))),
                "appears_all_16_years": bool(g["fiscal_year"].nunique() == len(EXPECTED_YEARS)),
            })
        write_csv(pd.DataFrame(presence).sort_values(["year_count", "normalized_label"]), out / "06_variable_presence_and_position.csv")
        year_label = dlong[["fiscal_year", "normalized_label", "prepared_column_name", "source_column_position"]].drop_duplicates()
        transitions = []
        for y in EXPECTED_YEARS[1:]:
            prev = year_label[year_label.fiscal_year == y-1]
            curr = year_label[year_label.fiscal_year == y]
            prev_labels = set(prev.normalized_label)
            curr_labels = set(curr.normalized_label)
            for label in sorted(curr_labels - prev_labels):
                rr = curr[curr.normalized_label == label].iloc[0]
                transitions.append({"from_year": y-1, "to_year": y, "change": "ADDED_OR_RENAMED",
                                   "normalized_label": label, "label_in_to_year": rr.prepared_column_name,
                                   "position_in_to_year": rr.source_column_position})
            for label in sorted(prev_labels - curr_labels):
                rr = prev[prev.normalized_label == label].iloc[0]
                transitions.append({"from_year": y-1, "to_year": y, "change": "MISSING_OR_RENAMED",
                                   "normalized_label": label, "label_in_from_year": rr.prepared_column_name,
                                   "position_in_from_year": rr.source_column_position})
            both = prev.merge(curr, on="normalized_label", suffixes=("_from", "_to"))
            for _, rr in both.iterrows():
                if str(rr["prepared_column_name_from"]) != str(rr["prepared_column_name_to"]):
                    transitions.append({"from_year": y-1, "to_year": y, "change": "LABEL_VARIANT",
                                        "normalized_label": rr.normalized_label,
                                        "label_in_from_year": rr["prepared_column_name_from"],
                                        "label_in_to_year": rr["prepared_column_name_to"]})
                if pd.notna(rr["source_column_position_from"]) and pd.notna(rr["source_column_position_to"]) and rr["source_column_position_from"] != rr["source_column_position_to"]:
                    transitions.append({"from_year": y-1, "to_year": y, "change": "POSITION_CHANGED",
                                        "normalized_label": rr.normalized_label,
                                        "label_in_from_year": rr["prepared_column_name_from"],
                                        "label_in_to_year": rr["prepared_column_name_to"],
                                        "position_in_from_year": rr["source_column_position_from"],
                                        "position_in_to_year": rr["source_column_position_to"]})
        write_csv(pd.DataFrame(transitions), out / "07_variable_year_to_year_changes.csv")
    else:
        dlong = pd.DataFrame()
        pd.DataFrame([{"warning": "prepared_column_name absent from dictionary"}]).to_csv(out / "06_variable_presence_and_position.csv", index=False)

    # 4) LGU presence and transitions using the supplied provisional key.
    # A key's absence/presence is NOT proof of creation/dissolution; names/boundaries can change.
    keysets = {int(y): set(g["lgu_key"].dropna().astype(str)) for y, g in panel.groupby("fiscal_year")}
    entity_cols = ["lgu_key", "lgu_name", "lgu_type", "province", "region", "source_excel_row"]
    entity_year = panel[entity_cols + ["fiscal_year"]].drop_duplicates(["fiscal_year", "lgu_key"])
    presence_rows = []
    for year in EXPECTED_YEARS:
        current = entity_year[entity_year.fiscal_year == year]
        prev_keys = keysets.get(year-1, set())
        curr_keys = keysets.get(year, set())
        for _, r in current.iterrows():
            presence_rows.append({"fiscal_year": year, "lgu_key": r.lgu_key,
                                  "lgu_name": r.lgu_name, "lgu_type": r.lgu_type,
                                  "province": r.province, "region": r.region,
                                  "status_vs_previous_year": "PRESENT_PREVIOUS_AND_CURRENT" if str(r.lgu_key) in prev_keys else ("FIRST_SEEN_IN_PANEL" if year == START_YEAR else "NEW_KEY_OR_REAPPEARING"),
                                  "warning": "Key status is provisional; not a legal creation/dissolution determination."})
    write_csv(pd.DataFrame(presence_rows), out / "08_lgu_annual_presence.csv")

    transitions = []
    for y in EXPECTED_YEARS[1:]:
        prev = entity_year[entity_year.fiscal_year == y-1].copy()
        curr = entity_year[entity_year.fiscal_year == y].copy()
        prev_keys = set(prev.lgu_key.dropna().astype(str))
        curr_keys = set(curr.lgu_key.dropna().astype(str))
        for key in sorted(prev_keys - curr_keys):
            r = prev[prev.lgu_key.astype(str) == key].iloc[0]
            transitions.append({"from_year": y-1, "to_year": y, "status": "KEY_ABSENT_IN_TO_YEAR",
                                "lgu_key": key, "from_name": r.lgu_name, "from_type": r.lgu_type,
                                "from_province": r.province, "from_region": r.region,
                                "interpretation": "Could be missing record, name/type/province change, coverage difference, or legal LGU change; verify source."})
        for key in sorted(curr_keys - prev_keys):
            r = curr[curr.lgu_key.astype(str) == key].iloc[0]
            transitions.append({"from_year": y-1, "to_year": y, "status": "NEW_KEY_IN_TO_YEAR",
                                "lgu_key": key, "to_name": r.lgu_name, "to_type": r.lgu_type,
                                "to_province": r.province, "to_region": r.region,
                                "interpretation": "Could be new LGU, renamed/reclassified/reassigned LGU, or extraction/coverage difference; verify source."})
        common = prev[prev.lgu_key.astype(str).isin(curr_keys)].merge(
            curr[curr.lgu_key.astype(str).isin(prev_keys)], on="lgu_key", suffixes=("_from", "_to"))
        for _, r in common.iterrows():
            changed = []
            for c in ["lgu_name", "lgu_type", "province", "region"]:
                a, b = r.get(c+"_from"), r.get(c+"_to")
                if norm_text(a) != norm_text(b):
                    changed.append(c)
            if changed:
                row = {"from_year": y-1, "to_year": y, "status": "ATTRIBUTES_CHANGED",
                       "lgu_key": r.lgu_key, "changed_fields": ";".join(changed)}
                for c in ["lgu_name", "lgu_type", "province", "region"]:
                    row["from_"+c] = r.get(c+"_from")
                    row["to_"+c] = r.get(c+"_to")
                transitions.append(row)
        # Candidate match: same normalized LGU name, but key changed (useful for name/type/province changes)
        prev2 = prev.copy()
        curr2 = curr.copy()
        prev2["name_norm"] = prev2.lgu_name.map(norm_text)
        curr2["name_norm"] = curr2.lgu_name.map(norm_text)
        candidates = prev2.merge(curr2, on="name_norm", suffixes=("_from", "_to"))
        for _, r in candidates.iterrows():
            if str(r.lgu_key_from) != str(r.lgu_key_to):
                transitions.append({
                    "from_year": y-1, "to_year": y, "status": "POSSIBLE_SAME_NAME_DIFFERENT_KEY",
                    "from_key": r.lgu_key_from, "to_key": r.lgu_key_to,
                    "from_name": r.lgu_name_from, "to_name": r.lgu_name_to,
                    "from_type": r.lgu_type_from, "to_type": r.lgu_type_to,
                    "from_province": r.province_from, "to_province": r.province_to,
                    "interpretation": "Candidate only; same-name LGUs can be distinct. Manually review."
                })
    trans_df = pd.DataFrame(transitions).drop_duplicates()
    write_csv(trans_df, out / "09_lgu_year_to_year_changes.csv")

    # Specific comparison: 2023 vs 2024 and each year vs 2023.
    base2023 = entity_year[entity_year.fiscal_year == 2023].copy()
    key2023 = set(base2023.lgu_key.dropna().astype(str))
    compare_rows = []
    for y in EXPECTED_YEARS:
        curr = entity_year[entity_year.fiscal_year == y].copy()
        curr_keys = set(curr.lgu_key.dropna().astype(str))
        for key in sorted(key2023 - curr_keys):
            r = base2023[base2023.lgu_key.astype(str) == key].iloc[0]
            compare_rows.append({"comparison": f"2023_vs_{y}", "comparison_year": y, "status": "IN_2023_NOT_IN_COMPARISON_YEAR",
                                "lgu_key": key, "lgu_name": r.lgu_name, "lgu_type": r.lgu_type,
                                "province": r.province, "region": r.region,
                                "interpretation": "Not proof of dissolution; check workbook and possible renaming/reclassification."})
        for key in sorted(curr_keys - key2023):
            r = curr[curr.lgu_key.astype(str) == key].iloc[0]
            compare_rows.append({"comparison": f"2023_vs_{y}", "comparison_year": y, "status": "IN_COMPARISON_YEAR_NOT_IN_2023",
                                "lgu_key": key, "lgu_name": r.lgu_name, "lgu_type": r.lgu_type,
                                "province": r.province, "region": r.region,
                                "interpretation": "Not proof of creation; check workbook and possible renaming/reclassification."})
    write_csv(pd.DataFrame(compare_rows), out / "10_2023_vs_all_years_lgu_differences.csv")

    # 5) Fiscal reconciliation checks. These are diagnostics only; assumptions are explicit.
    reconciliation_rows = []
    if "CURRENT OPERATING INCOME" in panel.columns and "TOTAL CURRENT OPERATING EXPENDITURES" in panel.columns and "NET OPERATING INCOME/ (LOSS) FROM CURRENT OPERATIONS" in panel.columns:
        inc = pd.to_numeric(panel["CURRENT OPERATING INCOME"], errors="coerce")
        exp = pd.to_numeric(panel["TOTAL CURRENT OPERATING EXPENDITURES"], errors="coerce")
        net = pd.to_numeric(panel["NET OPERATING INCOME/ (LOSS) FROM CURRENT OPERATIONS"], errors="coerce")
        residual = inc - exp - net
        for idx, r in panel.iterrows():
            if pd.notna(residual.loc[idx]) and pd.notna(inc.loc[idx]) and pd.notna(exp.loc[idx]) and pd.notna(net.loc[idx]):
                reconciliation_rows.append({
                    "fiscal_year": r.fiscal_year, "lgu_key": r.lgu_key, "lgu_name": r.lgu_name,
                    "province": r.province, "current_operating_income": inc.loc[idx],
                    "total_current_operating_expenditures": exp.loc[idx],
                    "reported_net_operating_income_loss": net.loc[idx],
                    "residual_income_minus_expenditure_minus_net": residual.loc[idx],
                    "within_tolerance": bool(abs(residual.loc[idx]) <= TOLERANCE),
                    "interpretation": "Arithmetic check only; if residual is nonzero, inspect source definitions/rounding."
                })
    recon = pd.DataFrame(reconciliation_rows)
    write_csv(recon, out / "11_current_operations_reconciliation.csv")
    if not recon.empty:
        recon_summary = recon.groupby("fiscal_year").agg(
            records_checked=("within_tolerance", "size"),
            within_tolerance=("within_tolerance", "sum"),
            outside_tolerance=("within_tolerance", lambda s: int((~s).sum())),
            median_abs_residual=("residual_income_minus_expenditure_minus_net", lambda s: float(s.abs().median())),
            max_abs_residual=("residual_income_minus_expenditure_minus_net", lambda s: float(s.abs().max()))
        ).reset_index()
    else:
        recon_summary = pd.DataFrame([{"warning": "Required operating income/expenditure/net columns not found; reconciliation skipped."}])
    write_csv(recon_summary, out / "12_reconciliation_summary.csv")

    # 6) Compare prepared row counts with extraction log and investigate 2013/2020 specifically.
    counts = panel.groupby("fiscal_year").size().rename("panel_count").reset_index()
    if "rows_extracted" in log.columns:
        counts = counts.merge(log[["fiscal_year", "rows_extracted", "last_populated_row", "reported_max_row",
                                  "reported_max_column", "notes"]], on="fiscal_year", how="left")
    counts["flag_2013"] = counts.fiscal_year.eq(2013)
    counts["flag_2020"] = counts.fiscal_year.eq(2020)
    counts["flag_2023"] = counts.fiscal_year.eq(2023)
    counts["flag_2024"] = counts.fiscal_year.eq(2024)
    write_csv(counts, out / "13_count_discrepancy_review.csv")

    # 7) Workbook dimensions from originals (optional but expected in user's project)
    write_csv(workbook_dimensions(root, log), out / "14_original_workbook_dimensions.csv")

    # 8) Human-readable summary
    lines = [
        "BLGF SRE PREPARED PANEL AUDIT",
        f"Project root: {root}",
        f"Input panel: {panel_path}",
        f"Rows: {len(panel):,}; columns: {len(panel.columns):,}",
        f"Years present: {sorted(panel.fiscal_year.dropna().astype(int).unique().tolist())}",
        f"Duplicate fiscal_year + lgu_key rows: {int(panel.duplicated(['fiscal_year','lgu_key']).sum()):,}",
        f"Missing fiscal_year values: {int(panel.fiscal_year.isna().sum()):,}",
        f"Distinct provisional LGU keys across all years: {panel.lgu_key.nunique(dropna=True):,}",
        "",
        "IMPORTANT LIMITATIONS",
        "- No unit conversion, inflation adjustment, imputation, or record deletion was performed.",
        "- Financial unit cannot be proven from the panel alone; compare source title, magnitudes, and arithmetic.",
        "- Key differences are candidate identity/coverage changes, not proof of legal creation or dissolution.",
        "- Name-only candidate matches may pair distinct LGUs; manually review all candidates.",
        "- Reconciliation tests are arithmetic diagnostics, not proof of accounting equivalence.",
        "",
        "YEAR COUNTS:"
    ]
    for _, r in year_counts.iterrows():
        lines.append(f"  {int(r.fiscal_year)}: {int(r.panel_rows)} rows")
    lines += ["", "OUTPUT FILES:"]
    for p in sorted(out.glob("*.csv")):
        lines.append(f"  {p.name}")
    (out / "AUDIT_SUMMARY.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nAudit complete. Outputs saved to: {out}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL AUDIT ERROR: {exc}", file=sys.stderr)
        raise
