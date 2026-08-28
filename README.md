# Provenance-aware reanalysis of public diabetic foot ulcer transcriptomics

Code, curated analysis objects, finalized figures, and machine-readable supplementary tables accompanying the manuscript:

> How sample provenance, comparator choice, and inferential units alter conclusions from public diabetic foot ulcer transcriptomics: an empirical methodological reanalysis

## Scope

This repository distinguishes deposited accession records from independent biological evidence. It maps accession records to source-reported specimens or participants, resolves exact raw-object reuse, retains intact diabetic foot skin and intact nondiabetic foot skin as biologically distinct comparators, and preserves the relevant biological unit for statistical inference.

For the supporting single-cell analysis, raw counts were aggregated by participant and cell type so that cells and sequencing libraries were not treated as independent biological replicates. The healer-versus-nonhealer single-cell analysis was treated as supporting clinical context rather than external replication of the bulk ulcer-versus-intact-skin contrasts.

Across the six registered GEO series, 127 accession records mapped to 94 conservative analytic units. All six GSE68183 control objects were exact matches to six GSE80178 control objects, so the combined 18 accession rows represented 12 conservative analytic units rather than 18 independent observations.

Within GSE80178, no gene passed Benjamini-Hochberg FDR 0.05 in either of the all-12 primary contrasts or in the all-12 pooled-comparator sensitivity analysis. A targeted n=11 sensitivity analysis yielded one DFU-versus-NFS signal and nine pooled-comparator signals. The one-gene DFU-versus-NFS set was contained within the pooled nine-gene set, so their union comprised nine sensitivity-only genes.

After provenance correction, only one independent and biologically compatible core bulk study remained. Cross-study gene robustness and pathway robustness were therefore not estimable. This is an evidence limitation and does not establish biological absence.

The supporting single-cell analysis used 14 foot-skin libraries from 11 participants. Of 45,514 input cells, 39,238 were retained after quality control and doublet removal. Eight eligible cell types yielded 65,624 participant-level gene-by-cell-type tests. No association passed global correction, and the minimum global FDR was 0.309.

## Dataset roles

| GEO series | Role in this release | Quantitative boundary |
|---|---|---|
| GSE68183 | Provenance-alias source only | All six control objects are exact matches to GSE80178 controls and are never counted as independent validation |
| GSE80178 | Core primary within-study bulk analysis | DFU versus intact diabetic foot skin and DFU versus intact nondiabetic foot skin are modeled as separate primary contrasts; the pooled comparator is sensitivity-only |
| GSE134431 | Healing-outcome context only | The healer-versus-nonhealer question is not quantitatively combined with the core ulcer-versus-intact-skin contrasts |
| GSE143735 | Systemic context only | Forearm skin is not treated as a local diabetic foot ulcer comparator and is not pooled with foot or ulcer tissue |
| GSE199939 | Context only | Excluded from the quantitative core because specimen-level ulcer status was unresolved in the public metadata |
| GSE165816 | Supporting participant-level single-cell context | The supporting analysis used 14 foot-skin libraries from 11 participants; forearm and peripheral-blood libraries were excluded, and healer versus nonhealer was not treated as replication of the bulk contrasts |

## Repository contents

- `04_code/Python` and `04_code/R`: scientific analysis, figure-generation, and table-generation entry points together with their required helpers.
- `04_code/configs` and `04_code/parameter_manifests`: documented sample, comparator, quality-control, threshold, and model settings.
- `04_code/environments`: recorded software and package versions for the documented analyses.
- `06_locked_results`: compact finalized result objects and source data used to regenerate downstream figures, robustness summaries, and supplementary tables.
- `figures`: finalized PNG and PDF figure files together with plain-text figure legends.
- `supplementary_tables`: machine-readable CSV versions of Supplementary Tables S1-S4.
- `provenance`: documentation of public-release transformations and mappings between executed project code and the curated public repository.

Raw GEO data files are not redistributed in this repository. Development-only scripts, private execution archives, repeated intermediate quality-control outputs, and manuscript author information are not included.

## Reproduction routes

Two reproduction routes are provided.

### 1. Fast manuscript-output reproduction

Use the compact derived objects already included in the repository to regenerate the robustness synthesis, finalized figures, and supplementary tables without repeating raw-data preprocessing.

This route is intended for inspection of how the reported manuscript outputs arise from the finalized analysis results.

### 2. Full scientific rerun

Download the GEO raw and supplementary files described in [DATA_ACCESS.md](DATA_ACCESS.md), recreate the documented directory structure, and follow the execution sequence in [RUN_ORDER.md](RUN_ORDER.md).

The full route reconstructs the bulk RMA/limma analysis and the single-cell preprocessing and participant-level pseudobulk analysis from public source files. The scripts are designed not to overwrite existing output directories.

## Software

- Python 3.12 was used for provenance mapping, harmonization, sparse-data conversion, robustness synthesis, figure generation, and supplementary-table generation.
- R 4.5.3 was used for bulk microarray preprocessing and differential-expression analysis and for the single-cell analysis.
- Minimal Python dependencies are listed in `requirements-python.txt`.
- Recorded R package versions are listed in `requirements-r.txt` and in the module-specific environment records.
- The supplied Supplementary Figure S1 export workflow uses Arial on Windows. Cross-platform-readable PNG and PDF outputs, together with the corresponding source data, are included.

## Traceability

`MANUSCRIPT_CODE_MAP.csv` maps manuscript outputs to the corresponding public scripts, the scripts used in the documented project execution, and the finalized result objects from which the outputs were generated.

Semantic renaming and path-only edits made during preparation of the public repository are documented in `provenance/PUBLIC_RELEASE_TRANSFORMATIONS.md`.

Scientific settings, comparison directions, quality-control rules, statistical thresholds, and random seeds were not altered during public-release curation.

## Data and code availability

All expression data analyzed in the manuscript are publicly available through NCBI GEO under accession numbers GSE68183, GSE80178, GSE134431, GSE143735, GSE199939, and GSE165816.

Raw GEO data are not redistributed here. Analysis code, curated analysis objects, finalized figures, figure legends, and machine-readable supplementary tables are publicly available in this repository:

[https://github.com/Doctor6tj/dfu-provenance-aware-reanalysis](https://github.com/Doctor6tj/dfu-provenance-aware-reanalysis)

The source code is released under the MIT License.

## License

Source code in this repository is released under the [MIT License](LICENSE).

The underlying GEO datasets remain subject to the terms of their original repositories and source studies. Derived manuscript figures, supplementary tables, and included analysis objects are provided for reproducibility and may also be subject to applicable source and journal terms.
