# How sample provenance, comparator choice, and inferential units alter conclusions from public diabetic foot ulcer transcriptomics

This repository contains the analysis code, provenance tables, participant/sample interface, figure sources, and machine-readable results for an empirical methodological reanalysis of six public diabetic foot ulcer and related skin transcriptomic series.

The study evaluates how three upstream analytical decisions change the apparent evidence base:

1. counting accession records versus resolving exact source-object reuse;
2. pooling biologically distinct intact-skin comparators versus retaining separate estimands; and
3. treating cells or libraries as observations versus preserving participants as the inferential unit.

## Main interpretive boundary

Six GSE68183 control profiles were exact complete-byte SHA-256 matches to six GSE80178 control profiles and therefore did not constitute an independent validation dataset. In the primary all-12 GSE80178 analyses, no gene passed Benjamini-Hochberg FDR 0.05. Threshold-crossing genes appeared only in the targeted n=11 single-profile exclusion sensitivity analysis and were retained as sensitivity findings.

After provenance and biological-compatibility screening, only one independent compatible core bulk study remained. Consequently, cross-study gene and pathway robustness were **not estimable**; this is not a finding that 0 of 18,865 genes were biologically reproducible. The 18,865 genes are the within-study tested universe.

In the supporting participant-level single-cell analysis, 14 foot-skin libraries from 11 participants yielded 65,624 eligible gene-by-cell-type tests. No association passed the global Benjamini-Hochberg correction (minimum global FDR 0.309). This analysis provides healing-outcome context and is not an independent replication of the bulk ulcer-versus-intact-skin contrasts.

## Evidence-status conventions

- **Within-study association:** evaluated in the all-sample GSE80178 contrasts.
- **Sensitivity evidence:** results dependent on the targeted GSM2114233 exclusion or pooled DFS/NFS comparator.
- **Supporting context:** participant-level GSE165816 healing-outcome analysis.
- **Cross-study robustness:** requires at least two independent studies with compatible tissues, comparators, and inferential units; this requirement was not met in the included bulk evidence.
- **Not estimable:** the required design structure was absent. This term must not be replaced by a zero-result count.

## Dataset roles

| GEO series | Role in this release | Quantitative boundary |
|---|---|---|
| GSE68183 | Provenance-alias source only | Its six control objects duplicate six GSE80178 controls and are never counted as independent validation |
| GSE80178 | Core within-study bulk analysis | DFU versus diabetic intact-foot skin and DFU versus nondiabetic intact-foot skin are modeled separately |
| GSE134431 | Healing-related context | Not quantitatively combined with the core contrast |
| GSE143735 | Systemic intact-skin context | Forearm skin is not treated as a local DFU comparator |
| GSE199939 | Context only | Excluded from the quantitative core because specimen-level ulcer status was unresolved |
| GSE165816 | Supporting participant-level single-cell analysis | Fourteen foot-skin libraries from 11 participants; healer versus nonhealer is not a replication of the bulk contrast |

## Repository contents

- `04_code/Python` and `04_code/R`: curated scientific entry points and required helpers.
- `04_code/configs` and `04_code/parameter_manifests`: archived sample, comparator, and model settings.
- `04_code/environments`: captured package versions from the accepted runs.
- `06_locked_results`: accepted interfaces and source data needed for downstream reproduction.
- `figures`: author-approved final PNG/PDF figure files and plain-text legends.
- `supplementary_tables`: submission-facing CSV tables.
- `provenance`: public-release transformations and execution-to-public-code mapping.

Raw GEO files, the private immutable execution archive, trial scripts, repeated QC attempts, and manuscript author information are intentionally not included.

## Reproduction routes

1. **Fast manuscript-object reproduction.** Use the accepted compact source objects already included to rebuild robustness synthesis, figures, and supplementary tables without rerunning raw-data preprocessing.
2. **Full scientific rerun.** Download the GEO raw/supplementary files described in [DATA_ACCESS.md](DATA_ACCESS.md), recreate the documented directory layout, and follow [RUN_ORDER.md](RUN_ORDER.md).

The scripts refuse to overwrite existing output directories. The fast route is sufficient to inspect how the reported tables and figures arise from accepted results; the full route reconstructs bulk and single-cell preprocessing from public raw files.

## Software

- Python 3.12 was used for provenance, harmonization, sparse conversion, robustness synthesis, figures, and tables.
- R 4.5.3 was used for bulk microarray and single-cell analysis.
- Python dependencies are listed in `requirements-python.txt`.
- R package versions are listed in `requirements-r.txt` and the module-specific environment captures.

## Traceability

`MANUSCRIPT_CODE_MAP.csv` maps manuscript objects to public scripts, original executed scripts, and governing result locks. Semantic renaming and path-only public-release edits are described in `provenance/PUBLIC_RELEASE_TRANSFORMATIONS.md`. Scientific settings, comparison directions, thresholds, and seeds were not altered during curation.

## Data and code availability

All expression data are public through NCBI GEO. Raw data are not redistributed here. Code and accepted source objects are publicly available in this repository under the MIT License.

## Citation

DFU provenance-aware reanalysis [software]. GitHub. 2026.
https://github.com/Doctor6tj/dfu-provenance-aware-reanalysis

Associated manuscript:

Junjun Liu, Yingqian Wang, and Weichang Shen. *How sample provenance, comparator choice, and inferential units alter conclusions from public diabetic foot ulcer transcriptomics: an empirical methodological reanalysis.*

## License

Source code in this repository is released under the [MIT License](LICENSE). Public GEO data and derived manuscript figures and tables remain subject to applicable source and journal terms.
