#!/usr/bin/env python
"""
Build and audit a PSA PSGC reference hierarchy from the 2Q 2026 workbook.

Run from the project root:
    python scripts/06_build_psgc_hierarchy.py

Optional:
    python scripts/06_build_psgc_hierarchy.py --input data/PSA/PSGC-2Q-2026-Publication-Datafile.xlsx
    python scripts/06_build_psgc_hierarchy.py --outdir outputs/psgc_hierarchy_audit

This script does NOT reconcile SRE or mayoral data. It builds the reference
hierarchy and emits QA files so the hierarchy can be inspected first.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import pandas as pd

SHEET = "PSGC"
LEVELS = {"Reg", "Prov", "City", "Mun", "SubMun", "Bgy"}

def clean_code(series: pd.Series, width: int) -> pd.Series:
    """Keep identifiers as strings; remove Excel .0 artifacts and non-digits."""
    s = series.astype("string").str.strip()
    s = s.str.replace(r"\.0+$", "", regex=True)
    s = s.str.replace(r"\D", "", regex=True)
    s = s.fillna("")
    return s.where(s.eq(""), s.str.zfill(width))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/PSA/PSGC-2Q-2026-Publication-Datafile.xlsx")
    ap.add_argument("--outdir", default="outputs/psgc_hierarchy_audit")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.outdir)
    if not src.exists():
        print(f"ERROR: PSGC workbook not found: {src}")
        print("Run this script from the project root, or pass --input with the correct path.")
        return 2
    out.mkdir(parents=True, exist_ok=True)

    raw = pd.read_excel(src, sheet_name=SHEET, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]
    required = ["10-digit PSGC", "Name", "Correspondence Code", "Geographic Level"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}")
        print(f"Columns found: {list(raw.columns)}")
        return 2

    df = raw.copy()
    for c in df.columns:
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
    df["level"] = df["Geographic Level"].astype("string").str.strip()
    df["psgc10"] = clean_code(df["10-digit PSGC"], 10)
    df["correspondence9"] = clean_code(df["Correspondence Code"], 9)
    df["name"] = df["Name"].astype("string").str.strip()
    df["name"] = df["name"].fillna("")
    df = df[df["level"].isin(LEVELS)].copy()

    # PSGC coding checks:
    # region = first 2 digits followed by 8 zeroes
    # province = first 5 digits followed by 5 zeroes
    # city/municipality/sub-municipality = first 7 digits followed by 3 zeroes
    # These are candidate parent codes and are accepted only when they exist
    # as records of the appropriate level in this same reference workbook.
    regions = df[df["level"].eq("Reg")].copy()
    provinces = df[df["level"].eq("Prov")].copy()
    cities_muns = df[df["level"].isin(["City", "Mun"])].copy()

    region_names = dict(zip(regions["psgc10"], regions["name"]))
    province_names = dict(zip(provinces["psgc10"], provinces["name"]))
    parent_lgus = df[df["level"].isin(["City", "Mun", "SubMun"])].copy()
    lgu_names = dict(zip(parent_lgus["psgc10"], parent_lgus["name"]))
    region_codes = set(regions["psgc10"])
    province_codes = set(provinces["psgc10"])
    lgu_codes = set(parent_lgus["psgc10"])

    df["region_code_candidate"] = df["psgc10"].str[:2] + "00000000"
    df["region_name_candidate"] = df["region_code_candidate"].map(region_names)
    df["region_parent_valid"] = df["region_code_candidate"].isin(region_codes)

    df["province_code_candidate"] = df["psgc10"].str[:5] + "00000"
    df["province_name_candidate"] = df["province_code_candidate"].map(province_names)
    df["province_parent_valid"] = df["province_code_candidate"].isin(province_codes)

    df["parent_lgu_code_candidate"] = df["psgc10"].str[:7] + "000"
    df["parent_lgu_name_candidate"] = df["parent_lgu_code_candidate"].map(lgu_names)
    df["parent_lgu_valid"] = df["parent_lgu_code_candidate"].isin(lgu_codes)

    def province_status(row):
        lev = row["level"]
        if lev in ("Reg", "Prov"):
            return "not_applicable"
        if row["province_parent_valid"]:
            return "verified_by_code_prefix"
        if lev == "City":
            return "independent_or_special_city_review"
        if lev == "Mun":
            return "special_or_unresolved_municipality_review"
        if lev == "SubMun":
            return "special_submunicipality_review"
        if lev == "Bgy":
            return "not_direct_parent_for_barangay"
        return "review"

    df["province_parent_status"] = df.apply(province_status, axis=1)

    def lgu_parent_status(row):
        if row["level"] != "Bgy":
            return "not_applicable"
        if row["parent_lgu_valid"]:
            return "verified_by_code_prefix"
        return "unresolved_barangay_parent"

    df["lgu_parent_status"] = df.apply(lgu_parent_status, axis=1)

    # Save reference layers. All identifiers remain strings.
    df.to_csv(out / "01_psgc_reference_with_candidates.csv", index=False, encoding="utf-8-sig")
    regions.to_csv(out / "02_psgc_regions.csv", index=False, encoding="utf-8-sig")
    provinces.to_csv(out / "03_psgc_provinces.csv", index=False, encoding="utf-8-sig")

    lgu_cols = [
        "psgc10", "correspondence9", "name", "level",
        "region_code_candidate", "region_name_candidate", "region_parent_valid",
        "province_code_candidate", "province_name_candidate", "province_parent_valid",
        "province_parent_status", "parent_lgu_code_candidate",
        "parent_lgu_name_candidate", "parent_lgu_valid", "lgu_parent_status",
        "Old names", "City Class", "Status",
    ]
    for c in lgu_cols:
        if c not in df.columns:
            df[c] = ""
    df[df["level"].isin(["City", "Mun"])][lgu_cols].to_csv(
        out / "04_psgc_cities_municipalities.csv", index=False, encoding="utf-8-sig"
    )
    df[df["level"].eq("Bgy")][lgu_cols].to_csv(
        out / "05_psgc_barangays.csv", index=False, encoding="utf-8-sig"
    )

    # QA summary by level, identifier validity, duplicate codes and correspondence-code collisions.
    counts = df["level"].value_counts().rename_axis("level").reset_index(name="records")
    counts.to_csv(out / "06_level_counts.csv", index=False, encoding="utf-8-sig")

    code_audit = pd.DataFrame([
        {"check": "blank_or_invalid_10_digit_PSGC", "count": int((df["psgc10"].str.len() != 10).sum())},
        {"check": "duplicate_10_digit_PSGC_rows", "count": int(df["psgc10"].duplicated(keep=False).sum())},
        {"check": "blank_or_invalid_9_digit_correspondence_code", "count": int((df["correspondence9"].str.len() != 9).sum())},
        {"check": "duplicate_nonblank_correspondence_code_rows", "count": int((df["correspondence9"].ne("") & df["correspondence9"].duplicated(keep=False)).sum())},
        {"check": "records_with_invalid_region_prefix", "count": int((~df["region_parent_valid"]).sum())},
        {"check": "province_rows_with_invalid_region_prefix", "count": int((~df.loc[df["level"].eq("Prov"), "region_parent_valid"]).sum())},
        {"check": "city_municipality_rows_with_province_prefix_found", "count": int(df["level"].isin(["City", "Mun"]).mul(df["province_parent_valid"]).sum())},
        {"check": "city_municipality_rows_without_province_prefix_found", "count": int((df["level"].isin(["City", "Mun"]) & ~df["province_parent_valid"]).sum())},
        {"check": "barangay_rows_with_city_municipality_parent_found", "count": int((df["level"].eq("Bgy") & df["parent_lgu_valid"]).sum())},
        {"check": "barangay_rows_without_city_municipality_parent_found", "count": int((df["level"].eq("Bgy") & ~df["parent_lgu_valid"]).sum())},
    ])
    code_audit.to_csv(out / "07_code_validation_summary.csv", index=False, encoding="utf-8-sig")

    # All items needing human review, not automatically assigned.
    review = df[
        (~df["region_parent_valid"])
        | (df["level"].isin(["City", "Mun"]) & ~df["province_parent_valid"])
        | (df["level"].eq("Bgy") & ~df["parent_lgu_valid"])
    ].copy()
    review.to_csv(out / "08_hierarchy_review_queue.csv", index=False, encoding="utf-8-sig")

    # Distinct nonblank correspondence code duplicates are listed separately for inspection.
    cc = df[df["correspondence9"].ne("")].copy()
    dup_cc = cc[cc["correspondence9"].duplicated(keep=False)].sort_values("correspondence9")
    dup_cc.to_csv(out / "09_duplicate_correspondence_codes.csv", index=False, encoding="utf-8-sig")

    summary_lines = [
        "PSGC HIERARCHY AUDIT",
        f"Input: {src}",
        f"Rows included (Reg/Prov/City/Mun/SubMun/Bgy): {len(df):,}",
        "",
        "LEVEL COUNTS:",
        counts.to_string(index=False),
        "",
        "CODE VALIDATION:",
        code_audit.to_string(index=False),
        "",
        f"Review queue rows: {len(review):,}",
        f"Output directory: {out}",
        "",
        "Interpretation rules:",
        "- Candidate parent codes are validated against actual records of the relevant level.",
        "- Missing province-prefix matches are flagged, not automatically treated as errors or assigned.",
        "- Correspondence Code is preserved independently and never derived from the 10-digit PSGC.",
        "- This is a current 2Q 2026 reference hierarchy; it does not itself establish historical LGU boundaries.",
    ]
    (out / "00_audit_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n".join(summary_lines))
    print("\nCreated hierarchy and QA files. No SRE or mayoral data were changed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
