"""PSGC reconciliation V4: safer candidate generation without prefix-derived parentage.

Run from the project root:
    python scripts/06_reconcile_lgu_geography_v4.py

Inputs (existing V3 outputs and PSA reference):
    outputs/psgc_reconciliation_v3/02_sre_candidates.csv
    outputs/psgc_reconciliation_v3/03_mayoral_candidates.csv
    data/PSA/PSGC-2Q-2026-Publication-Datafile.xlsx

V4 does NOT certify historical identity. It generates candidates from current names,
PSGC old-name fields, and explicit aliases. Province filtering is only applied when
an independently verified province crosswalk is supplied in the optional CSV noted
below. It never infers province ancestry from PSGC code prefixes.
"""
from pathlib import Path
import re
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PSGC_FILE = ROOT / "data" / "PSA" / "PSGC-2Q-2026-Publication-Datafile.xlsx"
V3_DIR = ROOT / "outputs" / "psgc_reconciliation_v3"
SRE_INPUT = V3_DIR / "02_sre_candidates.csv"
MAYOR_INPUT = V3_DIR / "03_mayoral_candidates.csv"
OUT = ROOT / "outputs" / "psgc_reconciliation_v4"
# Optional manually verified mapping file. It must contain columns:
# psgc_code, verified_province_name, evidence_source, evidence_note
PARENT_CROSSWALK = OUT / "verified_lgu_province_crosswalk.csv"

# Explicit name aliases are used only for candidate generation, never as proof of identity.
ALIASES = {
    "PRES CARLOS P GARCIA": "PRESIDENT CARLOS P GARCIA",
    "PRESIDENT CARLOS P GARCIA": "PRESIDENT CARLOS P GARCIA",
    "OZAMIS CITY": "OZAMIZ CITY",
    "OZAMIZ CITY": "OZAMIZ CITY",
    "CITY OF OZAMIZ": "OZAMIZ CITY",
    "GENERAL MARIANO ALVAREZ": "GENERAL MARIANO ALVAREZ",
    "GMA": "GENERAL MARIANO ALVAREZ",
    "BALIUAG": "BALIWAG",
    "BALIWAG": "BALIWAG",
    "CORDOBA": "CORDOBA",
    "PILILIA": "PILILLA",
    "PILILLA": "PILILLA",
    "PRES ROXAS": "PRESIDENT ROXAS",
    "PRESIDENT ROXAS": "PRESIDENT ROXAS",
    "PRES CARLOS P. GARCIA": "PRESIDENT CARLOS P GARCIA",
    "PIO V CORPUZ": "PIO V CORPUZ",
    "DON VICTORIANO CHIONGBIAN": "DON VICTORIANO CHIONGBIAN",
    "ROSELLER T LIM": "ROSELLER T LIM",
    "ISABELA CITY": "ISABELA CITY",
    "CITY OF ISABELA": "ISABELA CITY",
    "BACOLOD CITY": "BACOLOD CITY",
    "CITY OF BACOLOD": "BACOLOD CITY",
    "CITY OF SAN JUAN": "SAN JUAN CITY",
    "SAN JUAN CITY": "SAN JUAN CITY",
    "LAPU LAPU CITY OPON": "LAPU LAPU CITY",
    "LAPU LAPU": "LAPU LAPU CITY",
    "SANTO DOMINGO LIBOG": "SANTO DOMINGO",
    "DARAGA LOCSIN": "DARAGA",
    "SASMUAN SEXMOAN": "SASMUAN",
    "RODRIGUEZ MONTALBAN": "RODRIGUEZ",
    "LICUAN BAAY LICUAN": "LICUAN BAAY",
    "TOBIAS FORNIER DAO": "TOBIAS FORNIER",
    "BALIWAG BALIUAG": "BALIWAG",
}


def norm(value):
    if pd.isna(value):
        return ""
    s = str(value).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canonical(value):
    n = norm(value)
    return ALIASES.get(n, n)


def split_old_names(value):
    if pd.isna(value) or not str(value).strip():
        return []
    # PSA old names are usually separated by commas/semicolons; normalize each entry.
    pieces = re.split(r"[,;|]+", str(value))
    return [norm(x) for x in pieces if norm(x)]


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path, dtype=str, low_memory=False).fillna("")


def joined(values):
    vals = []
    for v in values:
        s = str(v).strip()
        if s and s not in vals:
            vals.append(s)
    return " || ".join(vals)


def candidate_summary(cands):
    return {
        "candidate_count": len(cands),
        "candidate_psgc_codes": joined(cands["psgc_code"].tolist()) if len(cands) else "",
        "candidate_psgc_names": joined(cands["psgc_name"].tolist()) if len(cands) else "",
        "candidate_levels": joined(cands["psgc_level"].tolist()) if len(cands) else "",
        "candidate_correspondence_codes": joined(cands["psgc_corr_code"].tolist()) if len(cands) else "",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (PSGC_FILE, SRE_INPUT, MAYOR_INPUT):
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")

    psgc = pd.read_excel(PSGC_FILE, sheet_name="PSGC", dtype=str).fillna("")
    psgc.columns = [str(c).strip() for c in psgc.columns]
    required = {"10-digit PSGC", "Correspondence Code", "Name", "Geographic Level", "Old names"}
    missing = required - set(psgc.columns)
    if missing:
        raise ValueError(f"PSGC workbook missing columns: {sorted(missing)}")

    units = psgc[psgc["Geographic Level"].str.strip().isin(["City", "Mun", "Prov"])].copy()
    units["psgc_code"] = units["10-digit PSGC"].astype(str).str.strip()
    units["psgc_corr_code"] = units["Correspondence Code"].astype(str).str.strip()
    units["psgc_name"] = units["Name"].astype(str).str.strip()
    units["psgc_level"] = units["Geographic Level"].astype(str).str.strip()
    units["name_norm"] = units["psgc_name"].map(norm)
    units["name_canonical"] = units["psgc_name"].map(canonical)
    units["old_name_list"] = units["Old names"].map(split_old_names)
    units["old_name_canonicals"] = units["old_name_list"].map(lambda xs: [canonical(x) for x in xs])
    local_units = units[units["psgc_level"].isin(["City", "Mun"])].copy()
    provinces = units[units["psgc_level"].eq("Prov")].copy()

    # Explicit verified crosswalk is the only allowed source for parent filtering.
    parent_map = {}
    if PARENT_CROSSWALK.exists():
        cross = read_csv(PARENT_CROSSWALK)
        needed = {"psgc_code", "verified_province_name", "evidence_source", "evidence_note"}
        if not needed.issubset(cross.columns):
            raise ValueError(f"{PARENT_CROSSWALK} must contain columns: {sorted(needed)}")
        cross["psgc_code"] = cross["psgc_code"].astype(str).str.strip()
        cross["verified_province_norm"] = cross["verified_province_name"].map(canonical)
        for _, row in cross.iterrows():
            if row["psgc_code"] and row["verified_province_norm"] and row["evidence_source"].strip():
                parent_map[row["psgc_code"]] = row["verified_province_norm"]

    def match_dataset(path, dataset):
        src = read_csv(path)
        results = []
        for idx, row in src.iterrows():
            # Preserve all V3 source/audit fields while recalculating candidates.
            if dataset == "SRE":
                province = row.get("source_province", "")
                name = row.get("source_lgu_name", "")
                lgu_type = row.get("source_lgu_type", "")
            else:
                province = row.get("source_province", "")
                name = row.get("source_lgu_name", "")
                lgu_type = "City/Municipality"
            pnorm, nraw = canonical(province), norm(name)
            ncanon = canonical(name)
            is_province = "PROVINCE" in norm(lgu_type)
            reference = provinces if is_province else local_units

            # First pass: exact normalized current name or explicit canonical alias.
            exact = reference[(reference["name_norm"] == nraw) | (reference["name_canonical"] == ncanon)].copy()
            basis = "exact_current_name_or_alias"

            # Second pass: old names are candidate evidence, including a source field
            # that contains the current name plus an appended historical alias.
            if exact.empty and not is_province:
                oldmask = reference["old_name_canonicals"].map(lambda xs: ncanon in xs or nraw in xs)
                exact = reference[oldmask].copy()
                if exact.empty:
                    # Composite source strings can include current name + old name.
                    # Compare tokens against current and old names but do not fuzzy-match.
                    source_tokens = set(nraw.split())
                    def composite_hit(r):
                        names = [r["name_norm"]] + r["old_name_list"]
                        return any(x and set(x.split()).issubset(source_tokens) for x in names)
                    exact = reference[reference.apply(composite_hit, axis=1)].copy()
                if not exact.empty:
                    basis = "old_name_or_composite_name_candidate"

            initial = exact.copy()
            province_filter = "not_needed"
            # Province narrowing is permitted only from a supplied evidence-backed crosswalk.
            if not is_province and len(initial) > 1:
                if not pnorm:
                    province_filter = "source_province_missing"
                else:
                    filtered = initial[initial["psgc_code"].map(lambda code: parent_map.get(code, "") == pnorm)].copy()
                    if len(filtered) == 1:
                        exact = filtered
                        province_filter = "narrowed_by_verified_crosswalk"
                    elif len(filtered) > 1:
                        exact = filtered
                        province_filter = "multiple_verified_candidates_in_source_province"
                    elif any(code in parent_map for code in initial["psgc_code"].tolist()):
                        # Crosswalk has evidence for at least one candidate, but none fit.
                        province_filter = "verified_crosswalk_conflicts_with_source_province"
                    else:
                        province_filter = "no_verified_parent_crosswalk_for_candidates"

            if len(exact) == 0:
                status, method = "unmatched", "no_name_or_alias_candidate"
            elif len(exact) > 1:
                status, method = "ambiguous", "multiple_name_or_alias_candidates"
            else:
                status = "unique_candidate"
                method = "unique_candidate_requires_historical_review"
                if basis == "old_name_or_composite_name_candidate":
                    method = "old_name_candidate_requires_historical_review"
                if province_filter == "narrowed_by_verified_crosswalk":
                    method = "verified_parent_crosswalk_candidate_requires_historical_review"

            record = row.to_dict()
            record.update({
                "v4_dataset": dataset,
                "v4_source_row_id": row.get("source_row_id", str(idx)),
                "v4_source_province": province,
                "v4_source_lgu_name": name,
                "v4_source_lgu_type": lgu_type,
                "v4_province_canonical": pnorm,
                "v4_name_canonical": ncanon,
                "v4_match_basis": basis,
                "v4_match_status": status,
                "v4_resolution_method": method,
                "v4_province_filter_status": province_filter,
                "v4_initial_candidate_count": len(initial),
                "v4_initial_candidate_psgc_codes": joined(initial["psgc_code"].tolist()) if len(initial) else "",
                "v4_initial_candidate_psgc_names": joined(initial["psgc_name"].tolist()) if len(initial) else "",
                "v4_initial_candidate_levels": joined(initial["psgc_level"].tolist()) if len(initial) else "",
                "v4_initial_candidate_correspondence_codes": joined(initial["psgc_corr_code"].tolist()) if len(initial) else "",
                **{f"v4_{k}": v for k, v in candidate_summary(exact).items()},
                "v4_historical_identity_verified": False,
                "v4_parentage_source": "verified_crosswalk" if province_filter == "narrowed_by_verified_crosswalk" else "not_established_by_code_prefix",
            })
            results.append(record)
        return pd.DataFrame(results)

    sre = match_dataset(SRE_INPUT, "SRE")
    mayor = match_dataset(MAYOR_INPUT, "MAYORAL")
    sre.to_csv(OUT / "01_sre_candidates_v4.csv", index=False, encoding="utf-8-sig")
    mayor.to_csv(OUT / "02_mayoral_candidates_v4.csv", index=False, encoding="utf-8-sig")

    summaries = []
    for label, frame in (("SRE", sre), ("MAYORAL", mayor)):
        total = len(frame)
        for status, count in frame["v4_match_status"].value_counts(dropna=False).items():
            summaries.append({"dataset": label, "status": status, "records": int(count), "total_records": total,
                              "share_pct": round(100 * int(count) / total, 2) if total else 0})
    pd.DataFrame(summaries).to_csv(OUT / "03_v4_match_summary.csv", index=False, encoding="utf-8-sig")

    # Compact review queue for all ambiguous/unmatched cases.
    for label, frame in (("sre", sre), ("mayoral", mayor)):
        q = frame[frame["v4_match_status"].isin(["ambiguous", "unmatched"])].copy()
        keep = [c for c in ["v4_source_province", "v4_source_lgu_name", "v4_source_lgu_type", "v4_match_status",
                            "v4_match_basis", "v4_province_filter_status", "v4_initial_candidate_psgc_names",
                            "v4_initial_candidate_levels", "v4_candidate_psgc_names", "v4_candidate_levels"] if c in q.columns]
        q[keep].drop_duplicates().to_csv(OUT / f"04_{label}_unresolved_review.csv", index=False, encoding="utf-8-sig")

    # Decision log template: no automatic historical certification.
    decisions = pd.concat([sre, mayor], ignore_index=True, sort=False)
    decisions = decisions[[c for c in ["v4_dataset", "v4_source_province", "v4_source_lgu_name", "v4_source_lgu_type",
                                      "v4_match_status", "v4_match_basis", "v4_candidate_psgc_codes",
                                      "v4_candidate_psgc_names"] if c in decisions.columns]].drop_duplicates()
    decisions["decision"] = "PENDING_REVIEW"
    decisions["verified_psgc_code"] = ""
    decisions["evidence_source"] = ""
    decisions["evidence_note"] = ""
    decisions["reviewer_date"] = ""
    decisions.to_csv(OUT / "05_v4_decision_log_template.csv", index=False, encoding="utf-8-sig")

    # Crosswalk template is intentionally empty; do not populate it from code prefixes.
    if not PARENT_CROSSWALK.exists():
        pd.DataFrame(columns=["psgc_code", "verified_province_name", "evidence_source", "evidence_note"]).to_csv(
            PARENT_CROSSWALK, index=False, encoding="utf-8-sig")

    print("\nPSGC V4 SUMMARY (candidates are not historical certification)")
    print(pd.DataFrame(summaries).to_string(index=False))
    print(f"\nOutputs: {OUT}")
    print("V4 does not infer province parentage from PSGC prefixes.")
    print("Unique candidates still require historical identity review before analysis-ready certification.")

if __name__ == "__main__":
    main()
