
from pathlib import Path
import re
import unicodedata

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PSGC_FILE = ROOT / "data" / "PSA" / "PSGC-2Q-2026-Publication-Datafile.xlsx"
V3_DIR = ROOT / "outputs" / "psgc_reconciliation_v3"
OUT = ROOT / "outputs" / "psgc_reconciliation_v4"

SRE_INPUT = V3_DIR / "02_sre_candidates.csv"
MAYOR_INPUT = V3_DIR / "03_mayoral_candidates.csv"

CROSSWALK_FILE = OUT / "verified_lgu_province_crosswalk.csv"

OUT.mkdir(parents=True, exist_ok=True)


def norm(value):
    """Normalize names without assuming that different names are equivalent."""
    if pd.isna(value):
        return ""

    value = unicodedata.normalize("NFKD", str(value).strip().upper())
    value = "".join(
        char for char in value if not unicodedata.combining(char)
    )
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical(value):
    """
    Standardize well-documented source naming variants.
    Keep aliases explicit so the decisions remain auditable.
    """
    value = norm(value)

    aliases = {
        "PRES CARLOS P GARCIA": "PRESIDENT CARLOS P GARCIA",
        "PRESIDENT CARLOS P GARCIA": "PRESIDENT CARLOS P GARCIA",
        "OZAMIS CITY": "OZAMIZ",
        "CITY OF OZAMIZ": "OZAMIZ",
        "OZAMIZ CITY": "OZAMIZ",
        "GENERAL MARIANO ALVAREZ": "GENERAL MARIANO ALVAREZ",
        "GMA": "GENERAL MARIANO ALVAREZ",
        "BALIUAG": "BALIWAG",
        "BALIWAG": "BALIWAG",
        "CORDOBA": "CORDOVA",
        "CORDOVA": "CORDOVA",
        "PILILIA": "PILILLA",
        "PILILLA": "PILILLA",
        "PRES ROXAS": "PRESIDENT ROXAS",
        "PRESIDENT ROXAS": "PRESIDENT ROXAS",
        "PIO V CORPUZ": "PIO V CORPUZ",
        "DON VICTORIANO CHIONGBIAN": "DON VICTORIANO CHIONGBIAN",
        "ROSSELLER T LIM": "ROSSELLER T LIM",
        "CITY OF ISABELA": "ISABELA",
        "ISABELA CITY": "ISABELA",
        "CITY OF BACOLOD": "BACOLOD",
        "BACOLOD CITY": "BACOLOD",
        "CITY OF SAN JUAN": "SAN JUAN",
        "SAN JUAN CITY": "SAN JUAN",
        "LAPU LAPU CITY OPON": "LAPU LAPU",
        "LAPU LAPU CITY": "LAPU LAPU",
        "CITY OF LAPU LAPU": "LAPU LAPU",
        "SANTO DOMINGO LIBOG": "SANTO DOMINGO",
        "DARAGA LOCSIN": "DARAGA",
        "SASMUAN SEXMOAN": "SASMUAN",
        "RODRIGUEZ MONTALBAN": "RODRIGUEZ",
        "LICUAN BAAY LICUAN": "LICUAN BAAY",
        "TOBIAS FORNIER DAO": "TOBIAS FORNIER",
        "CAGAYAN DE ORO CITY": "CAGAYAN DE ORO",
        "CITY OF CAGAYAN DE ORO": "CAGAYAN DE ORO",
        "ILIGAN CITY": "ILIGAN",
        "CITY OF ILIGAN": "ILIGAN",
        "SORSOGON CITY": "SORSOGON",
        "CITY OF SORSOGON": "SORSOGON",
        "TAGBILARAN CITY": "TAGBILARAN",
        "CITY OF TAGBILARAN": "TAGBILARAN",
        "MALAYBALAY CITY": "MALAYBALAY",
        "CITY OF MALAYBALAY": "MALAYBALAY",
        "OROQUIETA CITY": "OROQUIETA",
        "CITY OF OROQUIETA": "OROQUIETA",
        "TANGUB CITY": "TANGUB",
        "CITY OF TANGUB": "TANGUB",
        "GINGOOG CITY": "GINGOOG",
        "CITY OF GINGOOG": "GINGOOG",
    }

    if value in aliases:
        return aliases[value]

    # Strip common administrative prefixes/suffixes only after
    # the explicit aliases above have been considered.
    value = re.sub(
        r"^(CITY OF THE|CITY OF|MUNICIPALITY OF)\s+", "", value
    )
    value = re.sub(r"\s+(CITY|MUNICIPALITY)$", "", value)
    return value.strip()


def split_names(value):
    if pd.isna(value):
        return []
    return [
        part.strip()
        for part in re.split(r"[,;|]", str(value))
        if part.strip()
    ]


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    return pd.read_csv(path, low_memory=False, dtype=str).fillna("")


def load_crosswalk():
    """
    Only use explicitly reviewed province relationships.
    Expected columns:
      psgc_code, verified_province_name, evidence_source, evidence_note
    """
    columns = [
        "psgc_code",
        "verified_province_name",
        "evidence_source",
        "evidence_note",
    ]

    if not CROSSWALK_FILE.exists():
        pd.DataFrame(columns=columns).to_csv(
            CROSSWALK_FILE, index=False, encoding="utf-8-sig"
        )
        return {}

    crosswalk = pd.read_csv(CROSSWALK_FILE, dtype=str).fillna("")
    missing = set(columns) - set(crosswalk.columns)
    if missing:
        raise ValueError(
            f"Crosswalk is missing columns: {sorted(missing)}"
        )

    result = {}
    for _, row in crosswalk.iterrows():
        code = row["psgc_code"].strip()
        province = canonical(row["verified_province_name"])

        # Do not treat a row without an evidence source as verified.
        if code and province and row["evidence_source"].strip():
            result.setdefault(code, set()).add(province)

    return result


def main():
    psgc = pd.read_excel(
        PSGC_FILE, sheet_name="PSGC", dtype=str
    ).fillna("")
    psgc.columns = [str(col).strip() for col in psgc.columns]

    required = {
        "10-digit PSGC",
        "Correspondence Code",
        "Name",
        "Geographic Level",
        "Old names",
    }
    missing = required - set(psgc.columns)
    if missing:
        raise ValueError(f"PSGC workbook missing columns: {sorted(missing)}")

    psgc["psgc_code"] = psgc["10-digit PSGC"].str.strip()
    psgc["psgc_corr_code"] = psgc["Correspondence Code"].str.strip()
    psgc["psgc_name"] = psgc["Name"].str.strip()
    psgc["psgc_level"] = psgc["Geographic Level"].str.strip()
    psgc["name_key"] = psgc["psgc_name"].map(canonical)
    psgc["old_name_keys"] = psgc["Old names"].map(
        lambda value: [canonical(x) for x in split_names(value)]
    )

    units = psgc[
        psgc["psgc_level"].isin(["Prov", "City", "Mun"])
    ].copy()
    provinces = units[units["psgc_level"] == "Prov"].copy()
    local_units = units[
        units["psgc_level"].isin(["City", "Mun"])
    ].copy()

    province_names = set(provinces["name_key"])
    verified_parent_map = load_crosswalk()

    # Make the reference-unit audit available separately.
    units.to_csv(
        OUT / "00_psgc_units_v4.csv",
        index=False,
        encoding="utf-8-sig",
    )

    def match_dataset(path, dataset):
        source = read_csv(path)
        results = []

        for row_id, row in source.iterrows():
            if dataset == "SRE":
                source_province = row.get("source_province", "")
                source_name = row.get("source_lgu_name", "")
                source_type = row.get("source_lgu_type", "")
            else:
                # V3 files use these source fields.
                source_province = row.get("source_province", "")
                source_name = row.get("source_lgu_name", "")
                source_type = row.get("source_lgu_type", "")

            # Some older V3 exports may have differently named columns.
            if not source_province:
                source_province = row.get("province", "")
            if not source_province:
                source_province = row.get("province_raw", "")
            if not source_name:
                source_name = row.get("lgu_name", "")
            if not source_name:
                source_name = row.get("city_raw", "")

            province_key = canonical(source_province)
            name_key = canonical(source_name)
            is_province = "PROVINCE" in norm(source_type)

            pool = provinces if is_province else local_units

            current = pool[pool["name_key"] == name_key].copy()
            method = "canonical_current_name"

            # Use exact normalized old-name aliases only if no current
            # name candidate exists. These remain historical candidates.
            if current.empty and not is_province:
                old_mask = local_units["old_name_keys"].map(
                    lambda names: name_key in names
                )
                current = local_units[old_mask].copy()
                method = "exact_old_name"

            # Resolve multiple candidates only with an explicitly
            # evidence-backed province crosswalk.
            if len(current) > 1 and province_key:
                filtered_codes = []
                for code in current["psgc_code"]:
                    verified_provinces = verified_parent_map.get(
                        code, set()
                    )
                    if province_key in verified_provinces:
                        filtered_codes.append(code)

                if filtered_codes:
                    current = current[
                        current["psgc_code"].isin(filtered_codes)
                    ].copy()
                    method += "_verified_province_crosswalk"

            if not name_key:
                status = "missing_source_name"
            elif len(current) == 0:
                status = "unmatched"
            elif len(current) == 1:
                status = "unique_candidate_requires_historical_review"
            else:
                status = "ambiguous"

            results.append({
                "dataset": dataset,
                "source_row_id": row_id,
                "source_province": source_province,
                "source_lgu_name": source_name,
                "source_lgu_type": source_type,
                "source_name_key": name_key,
                "source_province_key": province_key,
                "v4_match_status": status,
                "v4_match_method": method,
                "v4_candidate_count": len(current),
                "v4_candidate_psgc_codes": " || ".join(
                    current["psgc_code"].tolist()
                ),
                "v4_candidate_psgc_names": " || ".join(
                    current["psgc_name"].tolist()
                ),
                "v4_candidate_levels": " || ".join(
                    current["psgc_level"].tolist()
                ),
                "v4_candidate_provinces_verified": " || ".join(
                    sorted({
                        province
                        for code in current["psgc_code"]
                        for province in verified_parent_map.get(code, set())
                    })
                ),
            })

        result = pd.DataFrame(results)

        # Retain every original V3 field and append the V4 results.
        combined = pd.concat(
            [source.reset_index(drop=True), result.reset_index(drop=True)],
            axis=1,
        )
        combined.to_csv(
            OUT / (
                "01_sre_candidates_v4.csv"
                if dataset == "SRE"
                else "02_mayoral_candidates_v4.csv"
            ),
            index=False,
            encoding="utf-8-sig",
        )
        return combined

    sre = match_dataset(SRE_INPUT, "SRE")
    mayor = match_dataset(MAYOR_INPUT, "MAYORAL")

    summaries = []
    for label, frame in [("SRE", sre), ("MAYORAL", mayor)]:
        for status, count in frame["v4_match_status"].value_counts().items():
            summaries.append({
                "dataset": label,
                "status": status,
                "records": int(count),
                "total_records": len(frame),
                "percent": round(count / len(frame) * 100, 2),
            })

    summary = pd.DataFrame(summaries)
    summary.to_csv(
        OUT / "03_v4_match_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    for label, frame in [("SRE", sre), ("MAYORAL", mayor)]:
        review = frame[
            frame["v4_match_status"].isin(
                ["ambiguous", "unmatched", "missing_source_name"]
            )
        ].copy()
        review.to_csv(
            OUT / (
                "04_sre_unresolved_review.csv"
                if label == "SRE"
                else "04_mayoral_unresolved_review.csv"
            ),
            index=False,
            encoding="utf-8-sig",
        )

    print("\nPSGC V4 CANDIDATE SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nOutputs: {OUT}")
    print(f"Verified crosswalk: {CROSSWALK_FILE}")
    print(
        "\nImportant: unique candidates still require historical identity "
        "and boundary review."
    )


if __name__ == "__main__":
    main()
