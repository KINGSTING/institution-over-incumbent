from pathlib import Path
import re
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "outputs" / "psgc_reconciliation_v3"
OUT = INPUT_DIR / "final_exception_review"
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "SRE": INPUT_DIR / "02_sre_candidates.csv",
    "MAYORAL": INPUT_DIR / "03_mayoral_candidates.csv",
}

def norm(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().upper()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def first_existing(df, names, default=""):
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([default] * len(df), index=df.index)

def variants(series):
    vals = sorted({str(x).strip() for x in series if pd.notna(x) and str(x).strip()})
    return " || ".join(vals)

def main():
    frames = []
    for dataset, path in FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing input: {path}")
        df = pd.read_csv(path, low_memory=False, dtype={"source_row_id": str})
        df["dataset"] = dataset
        for col in [
            "source_province", "source_lgu_name", "match_status",
            "resolution_method", "province_filter_status",
            "initial_candidate_count", "initial_candidate_psgc_codes",
            "initial_candidate_psgc_names", "initial_candidate_provinces",
            "candidate_count", "candidate_psgc_codes", "candidate_psgc_names",
            "candidate_levels",
        ]:
            if col not in df.columns:
                df[col] = ""
        df["province_norm_review"] = df["source_province"].map(norm)
        df["lgu_norm_review"] = df["source_lgu_name"].map(norm)

        # Review all non-unique records and any old-name candidates flagged for review.
        review_mask = df["match_status"].ne("unique_candidate")
        review_mask |= df["resolution_method"].astype(str).str.contains(
            "requires_review|historical_review|unresolved", case=False, regex=True, na=False
        )
        review = df.loc[review_mask].copy()
        frames.append((dataset, df, review))

    all_summary = []
    detail_frames = []
    case_frames = []

    for dataset, all_df, review in frames:
        all_counts = all_df["match_status"].fillna("missing_status").value_counts()
        for status, count in all_counts.items():
            all_summary.append({
                "dataset": dataset,
                "summary_type": "all_records_by_status",
                "status": status,
                "record_count": int(count),
                "distinct_source_cases": int(
                    all_df.loc[all_df["match_status"].eq(status),
                               ["province_norm_review", "lgu_norm_review"]]
                    .drop_duplicates().shape[0]
                ),
            })

        if review.empty:
            continue

        # Retain record-level evidence for traceability.
        detail = review.copy()
        detail["known_issue_flag"] = ""
        detail["review_guidance"] = ""

        for idx, row in detail.iterrows():
            prov = row["province_norm_review"]
            name = row["lgu_norm_review"]
            if prov == "PAMPANGA" and name == "SANTO TOMAS":
                detail.at[idx, "known_issue_flag"] = "Historical source/reference discrepancy"
                detail.at[idx, "review_guidance"] = (
                    "BLGF source contains this LGU in 2009 and 2024; absent from current PSGC candidate list. "
                    "Do not force a current PSGC match; seek historical crosswalk or exclude only from analyses requiring verified PSGC."
                )
            elif prov == "BATANGAS" and name in {"SANTO TOMAS", "SANTO TOMAS CITY"}:
                detail.at[idx, "known_issue_flag"] = "Santo Tomas naming/type discrepancy"
                detail.at[idx, "review_guidance"] = (
                    "Inspect source-year naming and official historical PSGC/administrative records; do not infer identity from name alone."
                )
            elif prov == "BASILAN" and name == "ISABELA CITY":
                detail.at[idx, "known_issue_flag"] = "Special-city parent relationship"
                detail.at[idx, "review_guidance"] = (
                    "Current PSGC includes City of Isabela; verify with an official administrative crosswalk rather than code-prefix ancestry."
                )
            elif prov == "NEGROS OCCIDENTAL" and name == "BACOLOD CITY":
                detail.at[idx, "known_issue_flag"] = "HUC/special-city parent relationship"
                detail.at[idx, "review_guidance"] = (
                    "Current PSGC includes City of Bacolod; verify the province/city relationship using an official crosswalk, not code-prefix ancestry."
                )

        detail_frames.append(detail)

        # Group by normalized source province/name and candidate/method evidence.
        group_cols = [
            "dataset", "province_norm_review", "lgu_norm_review",
            "match_status", "resolution_method", "province_filter_status",
            "initial_candidate_count", "initial_candidate_psgc_codes",
            "initial_candidate_psgc_names", "initial_candidate_provinces",
            "candidate_count", "candidate_psgc_codes", "candidate_psgc_names",
            "candidate_levels",
        ]
        # Ensure grouping columns exist and treat missing values consistently.
        for col in group_cols:
            if col not in review.columns:
                review[col] = ""
        grouped = review.groupby(group_cols, dropna=False, sort=True).agg(
            source_record_count=("source_row_id", "size"),
            source_province_variants=("source_province", variants),
            source_lgu_name_variants=("source_lgu_name", variants),
        ).reset_index()

        grouped["known_issue_flag"] = ""
        grouped["review_guidance"] = ""
        for idx, row in grouped.iterrows():
            prov = row["province_norm_review"]
            name = row["lgu_norm_review"]
            if prov == "PAMPANGA" and name == "SANTO TOMAS":
                grouped.at[idx, "known_issue_flag"] = "Historical source/reference discrepancy"
                grouped.at[idx, "review_guidance"] = "Keep unresolved pending historical crosswalk; do not force a current PSGC match."
            elif prov == "BATANGAS" and name in {"SANTO TOMAS", "SANTO TOMAS CITY"}:
                grouped.at[idx, "known_issue_flag"] = "Santo Tomas naming/type discrepancy"
                grouped.at[idx, "review_guidance"] = "Verify historical naming/type against official records."
            elif prov == "BASILAN" and name == "ISABELA CITY":
                grouped.at[idx, "known_issue_flag"] = "Special-city parent relationship"
                grouped.at[idx, "review_guidance"] = "Verify with official administrative crosswalk; do not rely on prefix ancestry."
            elif prov == "NEGROS OCCIDENTAL" and name == "BACOLOD CITY":
                grouped.at[idx, "known_issue_flag"] = "HUC/special-city parent relationship"
                grouped.at[idx, "review_guidance"] = "Verify with official administrative crosswalk; do not rely on prefix ancestry."

        case_frames.append(grouped)

        for status, group in review.groupby("match_status", dropna=False):
            all_summary.append({
                "dataset": dataset,
                "summary_type": "review_records_by_status",
                "status": str(status),
                "record_count": int(len(group)),
                "distinct_source_cases": int(
                    group[["province_norm_review", "lgu_norm_review"]].drop_duplicates().shape[0]
                ),
            })

    if detail_frames:
        detail_all = pd.concat(detail_frames, ignore_index=True)
        detail_all.to_csv(OUT / "01_unresolved_record_detail.csv", index=False, encoding="utf-8-sig")
    else:
        detail_all = pd.DataFrame()

    if case_frames:
        cases = pd.concat(case_frames, ignore_index=True)
        cases = cases.sort_values(
            ["dataset", "match_status", "province_norm_review", "lgu_norm_review"],
            kind="stable"
        )
        cases.to_csv(OUT / "02_distinct_exception_cases.csv", index=False, encoding="utf-8-sig")

        # Separate operational lists for review.
        cases[cases["match_status"].astype(str).eq("unmatched")].to_csv(
            OUT / "03_unmatched_cases.csv", index=False, encoding="utf-8-sig"
        )
        cases[cases["match_status"].astype(str).eq("ambiguous")].to_csv(
            OUT / "04_ambiguous_cases.csv", index=False, encoding="utf-8-sig"
        )

        # Blank decision fields for a controlled manual review; no automatic exclusion.
        template = cases.copy()
        template["review_decision"] = ""
        template["evidence_checked"] = ""
        template["exclude_from_verified_geography_analysis"] = ""
        template["reviewer_notes"] = ""
        template.to_csv(OUT / "05_exception_decision_log_template.csv", index=False, encoding="utf-8-sig")

        distinct_summary = cases.groupby(["dataset", "match_status"], dropna=False).agg(
            distinct_exception_cases=("lgu_norm_review", "size"),
            affected_source_records=("source_record_count", "sum"),
        ).reset_index()
        distinct_summary.to_csv(OUT / "06_distinct_exception_summary.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(all_summary).to_csv(
        OUT / "07_record_coverage_summary.csv", index=False, encoding="utf-8-sig"
    )

    print("\nFINAL EXCEPTION REVIEW CREATED")
    print(f"Output folder: {OUT}")
    if case_frames:
        print("\nDistinct exception summary:")
        print(distinct_summary.to_string(index=False))
        print("\nKnown issues flagged in the review:")
        flags = cases[cases["known_issue_flag"].astype(str).ne("")]
        if flags.empty:
            print("No predefined known-issue labels matched; inspect the full exception table.")
        else:
            print(flags[[
                "dataset", "source_province_variants", "source_lgu_name_variants",
                "source_record_count", "known_issue_flag", "review_guidance"
            ]].to_string(index=False))
    print("\nNo records were deleted or automatically excluded.")
    print("Review decisions must be recorded in 05_exception_decision_log_template.csv.")

if __name__ == "__main__":
    main()
