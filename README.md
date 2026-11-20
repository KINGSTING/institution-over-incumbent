# Institutions Over Incumbents? Political Succession and Fiscal Accountability in Philippine Municipal Governments

## 📖 Project Overview
This repository contains the data pipeline, econometric scripts, audit-coding protocols, and visualization code for the research project: **"Institutions Over Incumbents? Political Succession and Fiscal Accountability in Philippine Municipal Governments."**

Local governments operate within formal fiscal, administrative, and auditing rules, yet elected mayors change over time. This study investigates the extent to which Philippine municipal governments maintain continuity in **fiscal management** and **financial accountability** across changes in political leadership and potential surname-based succession.

To balance national breadth with documentary depth, the design combines two complementary empirical components:
1. **Component A (Broad Fiscal Panel):** A longitudinal municipal panel linking Bureau of Local Government Finance (BLGF) Statements of Receipts and Expenditures (SRE, FY1992–2024) with OpenHalalan election-winner records (2004–2025).
2. **Component B (Stratified Longitudinal Audit Subsample):** A purposively bounded, stratified subsample of ~24 municipalities (6 per transition cell, drawn from an initial pool of 57 matched LGU pairs / 114 observations) tracking Commission on Audit (COA) Annual Audit Reports (AARs) across pre-transition ($t-1$) and post-transition ($t+1, t+2$) fiscal years.

---

## 🧩 Conceptual & Analytical Framework

### Four-Cell Political-Transition Matrix
Rather than treating surname similarity as verified kinship or proven political dynasty membership, the pipeline classifies leadership transitions into four transparent operational categories:

| Transition Category | Outgoing Mayor ($t-1$) | Incoming Mayor ($t$) | Operational Interpretation |
| :--- | :--- | :--- | :--- |
| **Cell 1: Potential Continuity** | Potentially dynastic | Potentially dynastic | Succession remains within a potentially dynastic pattern |
| **Cell 2: Potential Interruption** | Potentially dynastic | Non-dynastic | Shift away from potential dynastic incumbency |
| **Cell 3: Potential Entry** | Non-dynastic | Potentially dynastic | Transition into potential dynastic incumbency |
| **Cell 4: Non-Dynastic Continuity** | Non-dynastic | Non-dynastic | Leadership turnover without potential dynastic status |

### Core Hypotheses Tested
- **H1 (Fiscal Continuity):** Municipal fiscal management outcomes exhibit baseline persistence across fiscal years and leadership transitions.
- **H2 & H3 (Transition-Associated Change & Heterogeneity):** Fiscal shifts during the first complete post-transition fiscal years differ across the four transition categories, net of LGU fixed effects, year shocks, and baseline convergence controls.
- **H4 (Accountability Continuity):** Documented COA audit opinions, Notices of Disallowance (NDs), Notices of Suspension (NSs), and unliquidated cash advances exhibit varying degrees of persistence between $t-1$ and $t+1/t+2$.
- **H5 (Cross-Source Consistency):** Fiscal patterns observed in the broad BLGF SRE panel are systematically cross-checked against documentary audit findings in the matched COA subsample.

---

## 📊 Preliminary Merge & Sampling Diagnostics

- **Broad SRE–OpenHalalan Proxy Merge (FY2018, FY2021, FY2023):** Retained **5,140** municipal-year observations with **4,550** exact matches (**87.10%**, **87.16%**, and **91.31%** coverage rates, respectively) prior to historical expansion (1992–2024) and boundary-change reconciliation.
- **COA Longitudinal Sampling Pool:** **114** baseline observations across **57** matched LGU pairs, stratified by transition cell, island group, and pre-transition revenue class to construct the **24-LGU** complete-case longitudinal panel ($t-1, t+1, t+2$).

---

## 📂 Repository Structure
```text
institutions-over-incumbents/
│
├── data/
│   ├── raw/
│   │   ├── blgf_sre/                       # BLGF Statements of Receipts & Expenditures (1992–2024)
│   │   ├── openhalalan/                    # Municipal election-winner records (2004–2025)
│   │   └── coa_aars/                       # Downloaded COA Annual Audit Reports (PDFs)
│   └── processed/
│       ├── sre_election_panel.parquet      # Master municipal fiscal-election panel (psgc10)
│       ├── transition_matrix_4cell.parquet # Validated predecessor-successor classifications
│       ├── coa_sampling_pool_57pairs.csv   # Initial 57-pair eligibility & stratification frame
│       └── coa_coded_subsample.parquet     # Standardized COA audit indicators (t-1, t+1, t+2)
│
├── docs/
│   └── coa_extraction_codebook.md          # Standardized protocol for coding COA AARs & inter-coder rules
│
├── src/
│   ├── 01_build_transition_matrix.py       # Election-to-FY mapping & 4-cell transition classification
│   ├── 02_merge_sre_panel.py               # PSGC10 harmonization, boundary checks & SRE panel merge
│   ├── 03_stratify_coa_sample.py           # 5-stage stratified sampling from the 57-pair COA pool
│   ├── 04_estimate_panel_models.py         # TWFE regressions, event-time studies & province clustering
│   └── 05_plot_figures.py                  # Generates publication-ready figures (300 DPI)
│
├── output/
│   ├── diagnostics/
│   │   ├── merge_coverage_report.txt       # Unmatched LGU diagnostics & cell distribution counts
│   │   └── coa_attrition_log.csv           # Stage 1–5 COA sampling & report availability audit
│   ├── tables/
│   │   └── twfe_event_study_results.csv    # Regression estimates & robustness checks
│   └── figures/                            # Final manuscript figures (PNG)
│
├── README.md
└── requirements.txt

```

---

## 🛠️ Methodology & Pipeline

The analytical workflow separates data validation, stratified audit sampling, and econometric estimation to ensure full reproducibility and transparent tracking of missing or ambiguous cases.

### 1. Political-Transition Classification (`src/01_build_transition_matrix.py`)

* Maps OpenHalalan election cycles (2004–2025) to complete post-transition fiscal years, isolating mixed transition years from full incumbent fiscal years.
* Validates independent predecessor and successor indicators before assigning municipalities to Cells 1–4, flagging ambiguous surname matches for sensitivity analysis.

### 2. Broad SRE Panel Construction (`src/02_merge_sre_panel.py`)

* Harmonizes municipal identifiers using 10-digit Philippine Standard Geographic Codes (`psgc10`), accounting for municipal creations, mergers, and cityhood conversions.
* Computes core fiscal continuity indicators: local source revenue share, National Tax Allotment (NTA) dependency, expenditure composition, and fiscal balance ratios.

### 3. Five-Stage COA Stratification (`src/03_stratify_coa_sample.py`)

* Audits the existing **57-pair (114-observation)** COA dataset for transition-cell eligibility.
* Stratifies eligible LGUs across the four transition cells, balancing by geographic island group, pre-transition revenue class, and baseline fiscal capacity to select ~6 LGUs per cell (**~24 LGUs total**) with complete $t-1, t+1, t+2$ report coverage.

### 4. Econometric & Cross-Source Analysis (`src/04_estimate_panel_models.py`)

* Estimates Two-Way Fixed Effects (TWFE) and event-time specifications with standard errors clustered at the **provincial level** (with two-way clustering robustness checks).
* Tests conditional convergence / baseline fiscal capacity controls and compares quantitative SRE trajectories against coded COA audit indicators (audit opinions, disallowances, suspensions, and unliquidated cash advances).

---

## 🚀 How to Reproduce

### Prerequisites

Ensure Python 3.9+ is installed, then install the required packages:

```bash
pip install pandas numpy statsmodels linearmodels scipy matplotlib seaborn pyarrow

```

### Execution

Run the pipeline sequentially from the repository root:

**Step 1: Construct and validate the 4-cell transition matrix**

```bash
python -u src/01_build_transition_matrix.py

```

**Step 2: Merge BLGF SRE panel and run coverage diagnostics**

```bash
python -u src/02_merge_sre_panel.py

```

*Inspect `output/diagnostics/merge_coverage_report.txt` for cell counts and unmatched LGU diagnostics.*

**Step 3: Generate the stratified COA sampling frame**

```bash
python -u src/03_stratify_coa_sample.py

```

**Step 4: Estimate TWFE panel models, event studies, and robustness checks**

```bash
python -u src/04_estimate_panel_models.py

```

**Step 5: Render manuscript figures**

```bash
python -u src/05_plot_figures.py

```

---

## ⚠️ Ethical & Interpretive Notes

* **Operational Scope:** Surname-based matching identifies *potential* political succession patterns; it is not treated as conclusive proof of biological kinship, political capture, or illicit conduct.
* **Audit Interpretation:** COA audit opinions, Notices of Disallowance, and Notices of Suspension reflect documented compliance and accounting observations within specific audit cycles rather than direct measures of individual intent.
* **Data Governance:** Underlying fiscal, electoral, and audit records are derived from public releases by the BLGF, COMELEC/OpenHalalan, and COA.
