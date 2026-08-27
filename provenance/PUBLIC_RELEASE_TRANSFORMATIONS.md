# Public-release transformations

The private project retains immutable, byte-exact execution archives. This public repository is a curated downstream derivative. No original project file was overwritten.

Public-release changes were limited to:

1. selecting final scientific entry points and required helpers while excluding trial, repair-history, acceptance, repeated-equivalence, and archive-population scripts;
2. replacing machine-specific executable and library paths with `python`, `Rscript`, relative project paths, or documented command-line arguments;
3. removing legacy local source locations from the public source manifest while preserving public URLs, filenames, sizes, and hashes;
4. giving the final figure code semantic filenames and updating only its internal imports/path references;
5. replacing the internal workbook-tool-dependent GSE165816 participant-map extractor with a public `openpyxl` implementation that produced an equivalent logical table;
6. retaining accepted compact result/source objects needed for tables and figures while excluding raw GEO data and the full private QC archive.

Scientific comparison directions, cohort roles, thresholds, prespecified exclusions, random seeds, and interpretation boundaries were not changed. The mapping to original executed scripts and governing locks is in `MANUSCRIPT_CODE_MAP.csv`.

