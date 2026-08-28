# Run order

Run commands from the repository root. Use a new output directory for every run; the scientific entry points intentionally refuse overwrite. Raw-data analysis can be skipped when only the accepted manuscript objects need to be rebuilt.

## 1. Provenance audit and metadata adjudication

The promoted provenance entry point implements the exact-object overlap pilot. It does not promote its unimplemented `full` mode.

```bash
python 04_code/Python/m01_provenance_audit.py \
  --registry 03_data/metadata/CANDIDATE_DATASET_REGISTRY.csv \
  --mode pilot \
  --gse80178-raw-tar 03_data/raw_external_READ_ONLY/GSE80178/GSE80178_RAW.tar \
  --gse68183-raw-tar 03_data/raw_external_READ_ONLY/GSE68183/GSE68183_RAW.tar \
  --source-manifest 03_data/metadata/SOURCE_FILE_MANIFEST.csv \
  --output-dir outputs/M01_provenance_pilot
```

Extract the GSE165816 participant/sample authority from the public supplementary workbook:

```bash
python 04_code/Python/m01_extract_gse165816_participant_map.py \
  03_data/raw_external_READ_ONLY/primary_evidence/M01_remaining_datasets/PMC8748704_supplementaryFiles/41467_2021_27801_MOESM4_ESM.xlsx \
  outputs/gse165816_supplement_participant_map.csv \
  outputs/gse165816_supplement_participant_map_summary.json
```

The accepted adjudicated interfaces are included under `06_locked_results/modules/M01_PROVENANCE_AUDIT`. They are the inputs to M02. The remaining-dataset audit can be reconstructed with `m01_remaining_dataset_audit.py` after obtaining the four GEO family archives listed in `DATA_ACCESS.md`.

## 2. Cohort harmonization

```bash
python 04_code/Python/m02_build_cohort_harmonization_interfaces.py \
  --participant-map 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_metadata_adjudication/participant_sample_map_candidate.csv \
  --pair-map 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_metadata_adjudication/gse68183_gse80178_pair_adjudication.csv \
  --remaining-registry 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_remaining_dataset_audit/remaining_dataset_sample_registry.csv \
  --gse165816-map 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_remaining_dataset_audit/gse165816_participant_sample_map.csv \
  --candidate-registry 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_closeout/CANDIDATE_DATASET_REGISTRY_after_M01_closeout.csv \
  --m01-closeout-lock 06_locked_results/modules/M01_PROVENANCE_AUDIT/v1_closeout/M01_CLOSEOUT_RESULT_LOCK_v1.json \
  --parameters 04_code/parameter_manifests/M02_cohort_harmonization_parameters_v1.json \
  --comparator-rules 04_code/configs/M02_comparator_compatibility_rules_v1.json \
  --output-dir outputs/M02_harmonization
```

## 3. GSE80178 bulk within-study analysis

Primary all-12 profile:

```bash
Rscript --vanilla 04_code/R/m03_run_gse80178_core_v3.R \
  03_data/raw_external_READ_ONLY/GSE80178/GSE80178_RAW.tar \
  04_code/configs/M03_GSE80178_sample_manifest_v1.csv \
  04_code/parameter_manifests/M03_WITHIN_STUDY_EFFECTS_primary_parameters_v2.json \
  outputs/M03_primary_all12
```

Targeted n=11 quality-control sensitivity profile (GSM2114233 omitted; the all-12 analysis remains primary):

```bash
Rscript --vanilla 04_code/R/m03_run_gse80178_core_v3.R \
  03_data/raw_external_READ_ONLY/GSE80178/GSE80178_RAW.tar \
  04_code/configs/M03_GSE80178_sample_manifest_sensitivity_exclude_GSM2114233_v1.csv \
  04_code/parameter_manifests/M03_WITHIN_STUDY_EFFECTS_sensitivity_exclude_GSM2114233_parameters_v2.json \
  outputs/M03_sensitivity_n11
```

## 4. Naive-versus-aware sensitivity

```bash
Rscript --vanilla 04_code/R/m04_run_naive_vs_aware_sensitivity_v1.R \
  03_data/raw_external_READ_ONLY/GSE68183/GSE68183_RAW.tar \
  03_data/raw_external_READ_ONLY/GSE80178/GSE80178_RAW.tar \
  04_code/parameter_manifests/M04_NAIVE_VS_AWARE_SENSITIVITY_parameters_v1.json \
  outputs/M04_naive_vs_aware
```

## 5. Robustness synthesis from accepted upstream results

This is the fastest scientific rerun and does not reconstruct expression matrices.

```bash
python 04_code/Python/m05_run_robustness_synthesis_v1.py \
  04_code/parameter_manifests/M05_ROBUSTNESS_SYNTHESIS_parameters_v1.json \
  outputs/M05_robustness
```

## 6. Supporting GSE165816 single-cell analysis

Convert the 14 public count matrices to the recorded sparse representation:

```bash
python 04_code/Python/m07_convert_full_core_to_sparse_mtx_v1.py \
  --project-root . \
  --library-manifest 04_code/configs/M07_full_core_foot_libraries_v1.csv \
  --output-dir outputs/M07_sparse
```

Run the participant-level analysis:

```bash
Rscript --vanilla 04_code/R/m07_run_full_core_analysis_v1.R \
  . \
  outputs/M07_sparse \
  04_code/configs/M07_full_core_foot_libraries_v1.csv \
  05_analysis_steps/M07_SINGLE_CELL_CONTEXT/preflight/M07_SOURCE_LINKED_ANNOTATION_DICTIONARY_v1_20260826/M07_PRIMARY_FOOT_ANNOTATION_DICTIONARY_v1.csv \
  04_code/parameter_manifests/M07_SINGLE_CELL_CONTEXT_full_core_parameters_v1.json \
  outputs/M07_single_cell
```

## 7. Result figures, Figure 1, and supplementary tables

Figures 2-4 and S1 are rebuilt from accepted compact source data:

```bash
python 04_code/Python/export_result_figures.py \
  --project-root . \
  --staging-dir outputs/result_figures_staging \
  --output-dir outputs/result_figures

python 04_code/Python/finalize_result_figure_exports.py \
  --source-dir outputs/result_figures \
  --output-dir outputs/result_figures_final
```

The recorded Figure S1 PDF exporter uses the Windows Arial device. On other systems, inspect or reuse the included author-approved `figures/FigureS1.png` and `figures/FigureS1.pdf`.

To rebuild the study-design Figure 1, first create a candidate and then export the author-approved layout. Inkscape must be installed and its executable supplied explicitly:

```bash
python 04_code/Python/build_figure1.py \
  --project-root . \
  --output-dir outputs/Figure1_candidate \
  --inkscape /path/to/inkscape

python 04_code/Python/export_figure1.py \
  --project-root . \
  --candidate-dir outputs/Figure1_candidate \
  --output-dir outputs/Figure1_final \
  --inkscape /path/to/inkscape \
  --author-visual-lock APPROVED
```

Apply the G15 interpretation corrections after the base figure export. These steps do not rerun expression analyses:

```bash
python 04_code/Python/g15_revise_figure1_scientific_boundaries_v1.py \
  --project-root . \
  --output-dir outputs/Figure1_G15 \
  --inkscape /path/to/inkscape \
  --stage final

python 04_code/Python/g15_revise_figure4_estimability_v1.py \
  --project-root . \
  --output-dir outputs/Figure4_G15 \
  --stage final
```

Apply the G15 interpretation corrections after the base figure export. These steps do not rerun expression analyses:

```bash
python 04_code/Python/g15_revise_figure1_scientific_boundaries_v1.py \
  --project-root . \
  --output-dir outputs/Figure1_G15 \
  --inkscape /path/to/inkscape \
  --stage final

python 04_code/Python/g15_revise_figure4_estimability_v1.py \
  --project-root . \
  --output-dir outputs/Figure4_G15 \
  --stage final
```

Supplementary tables can be rebuilt without raw-expression analysis:

```bash
python 04_code/Python/prepare_supplementary_tables.py \
  --project-root . \
  --output-dir outputs/supplementary_tables
```

