
from pathlib import Path
import re
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PSGC_FILE = ROOT / "data" / "PSA" / "PSGC-2Q-2026-Publication-Datafile.xlsx"
SRE_FILE = ROOT / "outputs" / "sre_prepared" / "lgu_fiscal_panel_2009_2024.csv"
MAYOR_FILE = ROOT / "outputs" / "openhalalan_prepared" / "03_mayoral_winners_standardized.csv"
OUT = ROOT / "outputs" / "psgc_reconciliation_v2"
OUT.mkdir(parents=True, exist_ok=True)


def norm(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().upper()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    # Explicitly documented aliases for source naming conventions.
    aliases = {
        "METRO MANILA": "NATIONAL CAPITAL REGION",
        "NCR": "NATIONAL CAPITAL REGION",
        "CITY OF CALOOCAN": "CALOOCAN",
        "CALOOCAN CITY": "CALOOCAN",
        "CITY OF LAMITAN": "LAMITAN",
        "LAMITAN CITY": "LAMITAN",
        "CITY OF MARAWI": "MARAWI",
        "MARAWI CITY": "MARAWI",
        "PUERTO PRINCESA CITY": "PUERTO PRINCESA",
    }
    if value in aliases:
        value = aliases[value]

    value = re.sub(r"^(CITY OF|CITY OF THE|MUNICIPALITY OF)\s+", "", value)
    value = re.sub(r"\s+(CITY|MUNICIPALITY)$", "", value)
    return value


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    return pd.read_csv(path, low_memory=False)


def main():
    psgc = pd.read_excel(PSGC_FILE, sheet_name="PSGC", dtype=str)
    psgc.columns = [str(c).strip() for c in psgc.columns]

    psgc["psgc_code"] = psgc["10-digit PSGC"].fillna("").str.strip()
    psgc["psgc_corr_code"] = psgc["Correspondence Code"].fillna("").str.strip()
    psgc["psgc_name"] = psgc["Name"].fillna("").str.strip()
    psgc["psgc_level"] = psgc["Geographic Level"].fillna("").str.strip()
    psgc["name_norm"] = psgc["psgc_name"].map(norm)
    psgc["old_names_norm"] = psgc["Old names"].fillna("").map(norm)

    # Restrict reference records to the intended geographic units.
    units = psgc[psgc["psgc_level"].isin(["Prov", "City", "Mun"])].copy()
    provinces = units[units["psgc_level"] == "Prov"].copy()
    local_units = units[units["psgc_level"].isin(["City", "Mun"])].copy()

    # Derive province ancestry from the correspondence-code hierarchy.
    # Use the PSGC code structure only to generate candidates; do not
    # silently certify a match from a prefix alone.
    def parent_candidates(code):
        code = str(code).strip()
        if len(code) < 4:
            return []
        prefix = code[:4]
        return provinces[
            provinces["psgc_code"].str.startswith(prefix, na=False)
        ].to_dict("records")

    parent_by_code = {}
    for _, row in local_units.iterrows():
        parents = parent_candidates(row["psgc_code"])
        parent_by_code[row["psgc_code"]] = parents

    # Save reference tables to make the process auditable.
    units.to_csv(OUT / "01_psgc_units.csv", index=False, encoding="utf-8-sig")

    def match_source(dataset, row_id, province, name, lgu_type=""):
        province_norm = norm(province)
        name_norm = norm(name)

        if not name_norm:
            return {
                "dataset": dataset, "source_row_id": row_id,
                "source_province": province, "source_lgu_name": name,
                "match_status": "missing_source_name",
                "candidate_count": 0, "candidate_psgc_codes": "",
                "candidate_psgc_names": "", "candidate_levels": "",
            }

        is_province = "PROVINCE" in norm(lgu_type)
        if is_province:
            candidates = provinces[provinces["name_norm"] == name_norm].copy()
        else:
            candidates = local_units[local_units["name_norm"] == name_norm].copy()

        # Match old names only when the normalized old-name field contains
        # the complete source name. These remain candidates for review.
        if candidates.empty and not is_province:
            old_match = local_units[
                local_units["old_names_norm"].str.contains(
                    re.escape(name_norm), na=False
                )
            ]
            candidates = old_match.copy()

        # Resolve repeated names only when the province relationship can
        # be established from the PSGC hierarchy.
        if len(candidates) > 1 and province_norm:
            province_matches = provinces[
                provinces["name_norm"] == province_norm
            ]
            if len(province_matches) == 1:
                province_code = province_matches.iloc[0]["psgc_code"]
                allowed_codes = {
                    p["psgc_code"]
                    for _, cand in candidates.iterrows()
                    for p in parent_by_code.get(cand["psgc_code"], [])
                }
                if province_code in allowed_codes:
                    filtered = candidates[
                        candidates["psgc_code"].isin(
                            [
                                code for code in candidates["psgc_code"]
                                if any(
                                    p["psgc_code"] == province_code
                                    for p in parent_by_code.get(code, [])
                                )
                            ]
                        )
                    ]
                    if not filtered.empty:
                        candidates = filtered

        if len(candidates) == 1:
            status = "unique_candidate"
        elif len(candidates) == 0:
            status = "unmatched"
        else:
            status = "ambiguous"

        return {
            "dataset": dataset,
            "source_row_id": row_id,
            "source_province": province,
            "source_lgu_name": name,
            "source_lgu_type": lgu_type,
            "source_name_normalized": name_norm,
            "source_province_normalized": province_norm,
            "match_status": status,
            "candidate_count": len(candidates),
            "candidate_psgc_codes": " || ".join(candidates["psgc_code"].tolist()),
            "candidate_psgc_names": " || ".join(candidates["psgc_name"].tolist()),
            "candidate_levels": " || ".join(candidates["psgc_level"].tolist()),
        }

    sre = read_csv(SRE_FILE)
    mayor = read_csv(MAYOR_FILE)

    sre_results = []
    for i, row in sre.iterrows():
        sre_results.append(match_source(
            "SRE", i, row.get("province", ""),
            row.get("lgu_name", ""), row.get("lgu_type", "")
        ))

    mayor_results = []
    for i, row in mayor.iterrows():
        mayor_results.append(match_source(
            "MAYORAL", i, row.get("province_raw", ""),
            row.get("city_raw", ""), "City/Municipality"
        ))

    sre_audit = pd.DataFrame(sre_results)
    mayor_audit = pd.DataFrame(mayor_results)

    sre_audit.to_csv(OUT / "02_sre_candidates.csv", index=False, encoding="utf-8-sig")
    mayor_audit.to_csv(OUT / "03_mayoral_candidates.csv", index=False, encoding="utf-8-sig")

    summaries = []
    for label, audit in [("SRE", sre_audit), ("MAYORAL", mayor_audit)]:
        for status, count in audit["match_status"].value_counts().items():
            summaries.append({
                "dataset": label,
                "status": status,
                "records": int(count),
                "total_records": len(audit),
                "percent": round(count / len(audit) * 100, 2),
            })

    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT / "04_match_summary.csv", index=False, encoding="utf-8-sig")

    print("\nPSGC V2 CANDIDATE SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nOutputs: {OUT}")
    print("Candidate matches are not certified until the hierarchy and exceptions are audited.")


if __name__ == "__main__":
    main()
