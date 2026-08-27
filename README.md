# Provenance-aware reanalysis of public diabetic-foot transcriptomes

Code and accepted source objects for the manuscript:

> Hidden sample reuse and comparator mismatch constrain apparent transcriptomic reproducibility in diabetic foot ulcers: a provenance-aware reanalysis

## Scope

This repository separates deposited accession records from independent biological evidence. It resolves exact raw-object reuse, keeps diabetic and nondiabetic intact-foot skin as distinct comparators, restores the participant as the inferential unit, and treats the single-cell healer-versus-nonhealer analysis as supporting context rather than external replication of the bulk contrasts.

The central result is an evidence boundary, not a claim that diabetic-foot-ulcer biology is absent. After provenance and comparator correction, one independent compatible core bulk study remained. Consequently, 0 of 18,865 genes could satisfy the prespecified cross-study robustness rule, and pathway robustness was not estimable. The supporting single-cell analysis retained 39,238 of 45,514 cells from 14 foot-skin libraries and 11 participants; none of 65,624 participant-level gene-by-cell-type tests survived global correction.

## Dataset roles

| GEO series | Role in this release | Quantitative boundary |
|---|---|---|
| GSE68183 | Provenance-alias source only | Its six control objects duplicate six GSE80178 controls and are never counted as independent validation |
| GSE80178 | Core within-study bulk analysis | DFU versus diabetic intact-foot skin and DFU versus nondiabetic intact-foot skin are modeled separately |
| GSE134431 | Healing-related context | Not quantitatively combined with the core contrast |
| GSE143735 | Systemic intact-skin context | Forearm skin is not treated as a local DFU comparator |
| GSE199939 | Diabetic-foot-skin background only | Excluded from the core analysis because sample-level ulcer status was not publicly verifiable |
| GSE165816 | Supporting participant-level single-cell analysis | Fourteen foot-skin libraries from 11 participants; healer versus nonhealer is not a replication of the bulk contrast |

## Repository contents

- `04_code/Python` and `04_code/R`: curated scientific entry points and their required helpers.
- `04_code/configs` and `04_code/parameter_manifests`: prespecified sample, comparator, and model settings.
- `04_code/environments`: captured package versions from the accepted runs.
- `06_locked_results`: compact accepted interfaces and source data needed for downstream reproduction.
- `figures`: author-approved final PNG/PDF figure files and plain-text legends.
- `supplementary_tables`: submission-facing CSV tables.
- `provenance`: public-release transformations and execution-to-public-code mapping.

Raw GEO files, the private immutable execution archive, trial scripts, repeated QC attempts, and manuscript author information are intentionally not included.

## Reproduction routes

Two routes are supported:

1. **Fast manuscript-object reproduction.** Use the accepted compact source objects already included to rebuild robustness synthesis, figures, and supplementary tables without rerunning raw-data preprocessing.
2. **Full scientific rerun.** Download the GEO raw/supplementary files described in [DATA_ACCESS.md](DATA_ACCESS.md), recreate the documented directory layout, and follow [RUN_ORDER.md](RUN_ORDER.md). The scripts refuse to overwrite existing output directories.

The fast route is sufficient to inspect how the reported tables and figures arise from accepted results. The full route is required to reconstruct bulk RMA/limma and single-cell preprocessing from public raw files.

## Software

- Python 3.12 was used for provenance, harmonization, sparse conversion, robustness synthesis, figures, and tables.
- R 4.5.3 was used for bulk microarray and single-cell analysis.
- Minimal Python dependencies are listed in `requirements-python.txt`.
- Recorded R package versions are listed in `requirements-r.txt` and in the module-specific environment captures.
- The recorded Figure S1 exporter uses the Windows Arial graphics device. Accepted cross-platform-readable PNG/PDF outputs and their source data are included.

## Traceability

`MANUSCRIPT_CODE_MAP.csv` maps manuscript objects to public scripts, original executed scripts, and the governing result locks. Semantic renaming and path-only public-release edits are described in `provenance/PUBLIC_RELEASE_TRANSFORMATIONS.md`. Scientific settings, comparison directions, thresholds, and seeds were not altered during curation.

## Data and code availability

All expression data are public through NCBI GEO. Raw data are not redistributed here. The verified public repository URL and any archival DOI will be added at the public-release gate.

## License

Source code in this repository is released under the [MIT License](LICENSE).
Public GEO data and derived manuscript figures and tables are included for
reproducibility and remain subject to applicable source and journal terms.
