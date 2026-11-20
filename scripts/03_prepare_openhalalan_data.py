
"""
Prepare OpenHalalan city/municipal mayoral panel and succession proxies.

Study:
Institutions over Incumbents? Political Succession and Fiscal
Accountability in Philippine Municipal Governments.

Source:
data/OpenHalalan/NLE_Winners_2004-2025.csv

Selected election years:
2016, 2019, 2022, 2025

Important:
- OpenHalalan is the sole source used in this script.
- APC data is not read or used.
- Same-surname succession is a proxy, not proof of kinship.
- LGU identifiers are provisional name-based keys and require PSGC
  reconciliation before substantive analysis.
- Ambiguous LGU-election groups are retained in the standardized
  file but excluded from transition calculations.
- The script does not modify the source CSV.
"""

from pathlib import Path
from itertools import pairwise
import re
import unicodedata

import pandas as pd


# ---------------------------------------------------------------------
# 1. PATHS AND SETTINGS
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "OpenHalalan"
    / "NLE_Winners_2004-2025.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "openhalalan_prepared"

SELECTED_YEARS = [2016, 2019, 2022, 2025]

MAYOR_POSITION_VALUES = {
    "MAYOR",
    "CITY MAYOR",
    "MUNICIPAL MAYOR",
}


# ---------------------------------------------------------------------
# 2. GENERAL HELPERS
# ---------------------------------------------------------------------

def normalize_text(value):
    """Normalize text for matching while preserving the original column."""
    if pd.isna(value):
        return ""

    text = str(value).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def safe_filename_text(value):
    return re.sub(r"[^A-Z0-9_]+", "_", str(value).upper())


def find_column(df, candidates, required=True):
    """Find a source column using case-insensitive candidate names."""
    normalized_columns = {
        normalize_text(column): column
        for column in df.columns
    }

    for candidate in candidates:
        key = normalize_text(candidate)
        if key in normalized_columns:
            return normalized_columns[key]

    if required:
        raise KeyError(
            f"Could not identify a required column. "
            f"Candidates: {candidates}. "
            f"Available columns: {list(df.columns)}"
        )

    return None


def clean_name_component(series):
    return series.fillna("").astype(str).map(normalize_text)


def write_csv(df, filename):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path}")


# ---------------------------------------------------------------------
# 3. READ SOURCE
# ---------------------------------------------------------------------

def read_source():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"OpenHalalan source file not found: {INPUT_FILE}"
        )

    print("Reading OpenHalalan...")

    df = pd.read_csv(
        INPUT_FILE,
        dtype=str,
        low_memory=False,
        encoding="utf-8-sig",
    )

    df.columns = [str(column).strip() for column in df.columns]

    print(f"Source rows: {len(df):,}")
    print(f"Source columns: {len(df.columns)}")

    return df


# ---------------------------------------------------------------------
# 4. IDENTIFY SOURCE COLUMNS
# ---------------------------------------------------------------------

def identify_columns(df):
    return {
        "last_name": find_column(
            df, ["Last Name", "Surname", "Family Name"]
        ),
        "first_name": find_column(
            df, ["First Name", "Given Name"]
        ),
        "middle_name": find_column(
            df, ["Middle Name"], required=False
        ),
        "full_name": find_column(
            df, ["Full Name", "Candidate Name", "Name"]
        ),
        "position": find_column(
            df, ["Position", "Office", "Elected Position"]
        ),
        "party": find_column(
            df, ["Party", "Political Party"], required=False
        ),
        "year": find_column(
            df, ["Year", "Election Year"]
        ),
        "province": find_column(
            df, ["Province"]
        ),
        "city": find_column(
            df, ["City", "Municipality", "City/Municipality"]
        ),
        "region": find_column(
            df, ["Region"], required=False
        ),
        "sex": find_column(
            df, ["Sex", "Gender"], required=False
        ),
    }


# ---------------------------------------------------------------------
# 5. SOURCE PROFILE
# ---------------------------------------------------------------------

def create_source_profile(df):
    rows = []

    for column in df.columns:
        rows.append({
            "column": column,
            "non_missing": int(df[column].notna().sum()),
            "missing": int(df[column].isna().sum()),
            "distinct_values": int(df[column].nunique(dropna=True)),
            "sample_values": " | ".join(
                df[column].dropna().astype(str).head(5).tolist()
            ),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# 6. STANDARDIZE MAYORAL RECORDS
# ---------------------------------------------------------------------

def prepare_mayoral_records(df, columns):
    print("Preparing OpenHalalan mayoral records...")

    data = df.copy()

    # Preserve original source row number for audit.
    data["source_row_number"] = range(2, len(data) + 2)

    # Standardize election year.
    data["year"] = pd.to_numeric(
        data[columns["year"]].astype(str).str.strip(),
        errors="coerce",
    )

    # Standardize position.
    data["position_raw"] = data[columns["position"]]
    data["position_normalized"] = (
        data[columns["position"]]
        .fillna("")
        .map(normalize_text)
    )

    # Select mayor records only.
    data = data[
        data["position_normalized"].isin(MAYOR_POSITION_VALUES)
    ].copy()

    # Restrict to selected election years.
    data = data[data["year"].isin(SELECTED_YEARS)].copy()
    data["year"] = data["year"].astype(int)

    # Retain original identifying fields.
    data["province_raw"] = data[columns["province"]]
    data["city_raw"] = data[columns["city"]]
    data["full_name_raw"] = data[columns["full_name"]]
    data["last_name_raw"] = data[columns["last_name"]]
    data["first_name_raw"] = data[columns["first_name"]]

    if columns["middle_name"]:
        data["middle_name_raw"] = data[columns["middle_name"]]
    else:
        data["middle_name_raw"] = ""

    if columns["party"]:
        data["party_raw"] = data[columns["party"]]
    else:
        data["party_raw"] = ""

    if columns["region"]:
        data["region_raw"] = data[columns["region"]]
    else:
        data["region_raw"] = ""

    if columns["sex"]:
        data["sex_raw"] = data[columns["sex"]]
    else:
        data["sex_raw"] = ""

    # Normalized geographic identifiers.
    data["province_normalized"] = (
        data["province_raw"].map(normalize_text)
    )
    data["city_normalized"] = (
        data["city_raw"].map(normalize_text)
    )

    # Provisional name-based LGU key.
    data["lgu_key"] = (
        data["province_normalized"]
        + "__"
        + data["city_normalized"]
    )

    data.loc[
        (data["province_normalized"] == "")
        | (data["city_normalized"] == ""),
        "lgu_key",
    ] = pd.NA

    # Normalized candidate name components.
    data["last_name_normalized"] = (
        data["last_name_raw"].map(normalize_text)
    )
    data["first_name_normalized"] = (
        data["first_name_raw"].map(normalize_text)
    )
    data["middle_name_normalized"] = (
        data["middle_name_raw"].map(normalize_text)
    )

    data["full_name_normalized"] = (
        data["full_name_raw"].map(normalize_text)
    )

    # Candidate matching keys.
    data["candidate_name_key"] = (
        data["last_name_normalized"]
        + "|"
        + data["first_name_normalized"]
        + "|"
        + data["middle_name_normalized"]
    )

    data["candidate_name_key"] = data[
        "candidate_name_key"
    ].replace({
        "||": "",
    })

    # Basic data-quality flags.
    data["missing_lgu_name"] = (
        data["province_normalized"].eq("")
        | data["city_normalized"].eq("")
    )

    data["missing_candidate_name"] = (
        data["last_name_normalized"].eq("")
        | data["first_name_normalized"].eq("")
    )

    data["missing_surname"] = (
        data["last_name_normalized"].eq("")
    )

    # Exact duplicate flag across the source fields used in analysis.
    duplicate_columns = [
        "year",
        "province_normalized",
        "city_normalized",
        "last_name_normalized",
        "first_name_normalized",
        "middle_name_normalized",
        "position_normalized",
    ]

    data["exact_duplicate_record"] = data.duplicated(
        subset=duplicate_columns,
        keep=False,
    )

    # Keep a record of how many analytical records exist per LGU-year.
    group_sizes = (
        data.dropna(subset=["lgu_key"])
        .groupby(["lgu_key", "year"])
        .size()
        .rename("records_in_lgu_year")
        .reset_index()
    )

    data = data.merge(
        group_sizes,
        on=["lgu_key", "year"],
        how="left",
    )

    data["records_in_lgu_year"] = (
        data["records_in_lgu_year"].fillna(0).astype(int)
    )

    # A group with more than one record is ambiguous for transition work.
    data["ambiguous_lgu_year"] = (
        data["records_in_lgu_year"] > 1
    )

    data["eligible_for_transition"] = (
        data["lgu_key"].notna()
        & ~data["missing_candidate_name"]
        & ~data["ambiguous_lgu_year"]
    )

    # Stable sort for reproducible output.
    data = data.sort_values(
        ["province_normalized", "city_normalized", "year"]
    ).reset_index(drop=True)

    return data


# ---------------------------------------------------------------------
# 7. BUILD TRANSITION PROXIES
# ---------------------------------------------------------------------

def build_transitions(mayors):
    print("Building mayoral transition proxies...")

    eligible = mayors[
        mayors["eligible_for_transition"]
    ].copy()

    transition_rows = []

    for previous_year, current_year in pairwise(SELECTED_YEARS):
        previous = eligible[
            eligible["year"] == previous_year
        ].copy()

        current = eligible[
            eligible["year"] == current_year
        ].copy()

        previous = previous.rename(columns={
            "full_name_raw": "previous_mayor_name",
            "last_name_raw": "previous_last_name",
            "first_name_raw": "previous_first_name",
            "middle_name_raw": "previous_middle_name",
            "last_name_normalized": "previous_last_name_normalized",
            "first_name_normalized": "previous_first_name_normalized",
            "middle_name_normalized": "previous_middle_name_normalized",
            "full_name_normalized": "previous_full_name_normalized",
            "candidate_name_key": "previous_candidate_name_key",
            "source_row_number": "previous_source_row_number",
        })

        current = current.rename(columns={
            "full_name_raw": "current_mayor_name",
            "last_name_raw": "current_last_name",
            "first_name_raw": "current_first_name",
            "middle_name_raw": "current_middle_name",
            "last_name_normalized": "current_last_name_normalized",
            "first_name_normalized": "current_first_name_normalized",
            "middle_name_normalized": "current_middle_name_normalized",
            "full_name_normalized": "current_full_name_normalized",
            "candidate_name_key": "current_candidate_name_key",
            "source_row_number": "current_source_row_number",
        })

        merged = previous[
            [
                "lgu_key",
                "province_raw",
                "city_raw",
                "previous_mayor_name",
                "previous_last_name",
                "previous_first_name",
                "previous_middle_name",
                "previous_last_name_normalized",
                "previous_first_name_normalized",
                "previous_middle_name_normalized",
                "previous_full_name_normalized",
                "previous_candidate_name_key",
                "previous_source_row_number",
            ]
        ].merge(
            current[
                [
                    "lgu_key",
                    "current_mayor_name",
                    "current_last_name",
                    "current_first_name",
                    "current_middle_name",
                    "current_last_name_normalized",
                    "current_first_name_normalized",
                    "current_middle_name_normalized",
                    "current_full_name_normalized",
                    "current_candidate_name_key",
                    "current_source_row_number",
                ]
            ],
            on="lgu_key",
            how="inner",
            validate="one_to_one",
        )

        merged["previous_year"] = previous_year
        merged["current_year"] = current_year

        # Same normalized full name: candidate identity proxy.
        merged["same_normalized_name"] = (
            merged["previous_candidate_name_key"]
            == merged["current_candidate_name_key"]
        )

        # Same surname: possible family succession proxy only.
        merged["same_surname_proxy"] = (
            merged["previous_last_name_normalized"].ne("")
            & merged["current_last_name_normalized"].ne("")
            & (
                merged["previous_last_name_normalized"]
                == merged["current_last_name_normalized"]
            )
        )

        merged["different_surname_proxy"] = (
            merged["previous_last_name_normalized"].ne("")
            & merged["current_last_name_normalized"].ne("")
            & (
                merged["previous_last_name_normalized"]
                != merged["current_last_name_normalized"]
            )
        )

        merged["succession_type"] = "different_surname"

        merged.loc[
            merged["same_surname_proxy"],
            "succession_type",
        ] = "same_surname_proxy"

        merged.loc[
            merged["same_normalized_name"],
            "succession_type",
        ] = "same_person_name_proxy"

        merged["surname_proxy_note"] = (
            "Same surname does not establish a familial relationship."
        )

        transition_rows.append(merged)

    if not transition_rows:
        return pd.DataFrame()

    transitions = pd.concat(
        transition_rows,
        ignore_index=True,
    )

    return transitions


# ---------------------------------------------------------------------
# 8. BUILD CONSOLIDATED LGU-YEAR PANEL
# ---------------------------------------------------------------------

def build_proxy_panel(mayors, transitions):
    print("Building consolidated mayoral proxy panel...")

    panel = mayors.copy()

    # One row per source mayor record is retained in this file.
    # Transition fields are attached only where a valid adjacent-cycle
    # transition exists.
    transition_columns = [
        "lgu_key",
        "current_year",
        "previous_year",
        "previous_mayor_name",
        "same_normalized_name",
        "same_surname_proxy",
        "different_surname_proxy",
        "succession_type",
    ]

    if transitions.empty:
        panel["previous_year"] = pd.NA
        panel["previous_mayor_name"] = pd.NA
        panel["same_normalized_name"] = pd.NA
        panel["same_surname_proxy"] = pd.NA
        panel["different_surname_proxy"] = pd.NA
        panel["succession_type"] = pd.NA
    else:
        transition_subset = transitions[
            transition_columns
        ].copy()

        panel = panel.merge(
            transition_subset,
            left_on=["lgu_key", "year"],
            right_on=["lgu_key", "current_year"],
            how="left",
            validate="one_to_one",
        )

        panel = panel.drop(columns=["current_year"])

    panel["proxy_panel_year"] = panel["year"]

    panel["transition_observed"] = (
        panel["previous_year"].notna()
    )

    panel["same_surname_proxy"] = panel[
        "same_surname_proxy"
    ].astype("boolean")

    panel["same_normalized_name"] = panel[
        "same_normalized_name"
    ].astype("boolean")

    panel["different_surname_proxy"] = panel[
        "different_surname_proxy"
    ].astype("boolean")

    panel["proxy_interpretation"] = (
        "Surname similarity is an indirect proxy only; "
        "it does not verify kinship."
    )

    # Keep a clear indicator that the LGU key is provisional.
    panel["lgu_key_status"] = "provisional_name_based_key"

    return panel.sort_values(
        ["province_normalized", "city_normalized", "year"]
    ).reset_index(drop=True)


# ---------------------------------------------------------------------
# 9. AUDIT TABLES
# ---------------------------------------------------------------------

def create_lgu_year_counts(mayors):
    counts = (
        mayors.groupby(
            ["province_raw", "city_raw", "lgu_key", "year"],
            dropna=False,
        )
        .agg(
            mayoral_records=("source_row_number", "size"),
            distinct_candidate_names=(
                "candidate_name_key", "nunique"
            ),
            ambiguous_lgu_year=("ambiguous_lgu_year", "max"),
            eligible_for_transition=(
                "eligible_for_transition", "max"
            ),
        )
        .reset_index()
    )

    return counts


def create_review_file(mayors):
    review = mayors[
        mayors["missing_lgu_name"]
        | mayors["missing_candidate_name"]
        | mayors["ambiguous_lgu_year"]
        | mayors["exact_duplicate_record"]
    ].copy()

    review["review_reason"] = ""

    review.loc[
        review["missing_lgu_name"],
        "review_reason",
    ] += "missing_lgu_name;"

    review.loc[
        review["missing_candidate_name"],
        "review_reason",
    ] += "missing_candidate_name;"

    review.loc[
        review["ambiguous_lgu_year"],
        "review_reason",
    ] += "multiple_records_in_lgu_year;"

    review.loc[
        review["exact_duplicate_record"],
        "review_reason",
    ] += "possible_exact_duplicate;"

    return review


def create_duplicate_file(mayors):
    return mayors[
        mayors["exact_duplicate_record"]
    ].copy()


# ---------------------------------------------------------------------
# 10. REPORT
# ---------------------------------------------------------------------

def create_report(
    source,
    mayors,
    transitions,
    panel,
    columns,
):
    lines = []

    lines.append("OPENHALALAN MAYORAL PROXY PANEL PREPARATION")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Source file: {INPUT_FILE}")
    lines.append(f"Source rows: {len(source):,}")
    lines.append(f"Source columns: {len(source.columns)}")
    lines.append("APC dataset used: NO")
    lines.append("")
    lines.append("Selected election years:")
    lines.append(", ".join(map(str, SELECTED_YEARS)))
    lines.append("")

    lines.append("Detected source columns:")
    for key, value in columns.items():
        lines.append(f"  {key}: {value}")
    lines.append("")

    lines.append("Mayoral panel:")
    lines.append(f"  Selected-period mayor records: {len(mayors):,}")
    lines.append(
        f"  Distinct provisional LGU keys: "
        f"{mayors['lgu_key'].nunique(dropna=True):,}"
    )
    lines.append(
        f"  Missing LGU names: "
        f"{mayors['missing_lgu_name'].sum():,}"
    )
    lines.append(
        f"  Missing candidate names: "
        f"{mayors['missing_candidate_name'].sum():,}"
    )
    lines.append(
        f"  Ambiguous LGU-election records: "
        f"{mayors['ambiguous_lgu_year'].sum():,}"
    )
    lines.append(
        f"  Exact duplicate flagged records: "
        f"{mayors['exact_duplicate_record'].sum():,}"
    )
    lines.append("")

    lines.append("Mayoral records by year:")
    for year, count in mayors.groupby("year").size().items():
        lines.append(f"  {year}: {count:,}")
    lines.append("")

    lines.append("Transition audit:")
    lines.append(f"  Transition rows: {len(transitions):,}")

    if not transitions.empty:
        lines.append(
            f"  Same normalized name: "
            f"{transitions['same_normalized_name'].sum():,}"
        )
        lines.append(
            f"  Same surname proxy: "
            f"{transitions['same_surname_proxy'].sum():,}"
        )
        lines.append(
            f"  Different surname: "
            f"{transitions['different_surname_proxy'].sum():,}"
        )
        lines.append("")
        lines.append("Transition rows by cycle:")
        for (previous_year, current_year), count in (
            transitions.groupby(["previous_year", "current_year"]).size().items()
        ):
            lines.append(
                f"  {previous_year}-{current_year}: {count:,}"
            )

    lines.append("")
    lines.append("Proxy panel:")
    lines.append(f"  Panel rows: {len(panel):,}")
    lines.append(
        f"  Rows with an observed preceding-cycle transition: "
        f"{panel['transition_observed'].sum():,}"
    )
    lines.append("")
    lines.append("Interpretation cautions:")
    lines.append(
        "  1. Same surname is not proof of familial relationship."
    )
    lines.append(
        "  2. Same normalized name is a name-based identity proxy, "
        "not independently verified identity."
    )
    lines.append(
        "  3. Province + city/municipality keys are provisional "
        "and require PSGC reconciliation."
    )
    lines.append(
        "  4. Ambiguous LGU-election groups are excluded from "
        "transition calculations."
    )
    lines.append(
        "  5. Missing or unobserved cycles are not bridged."
    )
    lines.append("")

    report_path = OUTPUT_DIR / "02_preparation_report.txt"
    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"Saved: {report_path}")


# ---------------------------------------------------------------------
# 11. MAIN
# ---------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source = read_source()
    columns = identify_columns(source)

    source_profile = create_source_profile(source)
    write_csv(
        source_profile,
        "01_source_column_profile.csv",
    )

    mayors = prepare_mayoral_records(source, columns)

    print("Building transition records...")
    transitions = build_transitions(mayors)

    print("Building consolidated proxy panel...")
    panel = build_proxy_panel(mayors, transitions)

    lgu_year_counts = create_lgu_year_counts(mayors)
    review = create_review_file(mayors)
    duplicates = create_duplicate_file(mayors)

    # Standardized mayoral records.
    write_csv(
        mayors,
        "03_mayoral_winners_standardized.csv",
    )

    # Adjacent-cycle transitions.
    write_csv(
        transitions,
        "04_mayoral_transitions_surname_proxy.csv",
    )

    # LGU-year record counts and ambiguity audit.
    write_csv(
        lgu_year_counts,
        "05_municipality_year_winner_counts.csv",
    )

    # Records requiring manual review.
    write_csv(
        review,
        "06_name_and_key_review.csv",
    )

    # Exact duplicate flags.
    write_csv(
        duplicates,
        "07_exact_duplicate_records.csv",
    )

    # Consolidated city/municipal mayoral proxy panel.
    write_csv(
        panel,
        "08_mayoral_proxy_panel.csv",
    )

    create_report(
        source,
        mayors,
        transitions,
        panel,
        columns,
    )

    print("")
    print("=" * 60)
    print("PREPARATION COMPLETE")
    print("=" * 60)
    print(f"Mayoral records: {len(mayors):,}")
    print(f"Transition records: {len(transitions):,}")
    print(f"Proxy panel records: {len(panel):,}")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
