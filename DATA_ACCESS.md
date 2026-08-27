# Data access and expected raw-data layout

All primary expression inputs are public. Download them from the NCBI Gene Expression Omnibus accession pages:

- [GSE68183](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE68183)
- [GSE80178](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE80178)
- [GSE134431](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE134431)
- [GSE143735](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE143735)
- [GSE199939](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE199939)
- [GSE165816](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE165816)

The public files are not bundled in this repository. Place downloaded files under the following read-only layout before a full rerun:

```text
03_data/
  raw_external_READ_ONLY/
    GSE68183/
      GSE68183_RAW.tar
      GSE68183_series_matrix.txt.gz
    GSE80178/
      GSE80178_RAW.tar
      GSE80178_series_matrix.txt.gz
    GSE134431/
      GSE134431_family.xml.tgz
    GSE143735/
      GSE143735_family.xml.tgz
    GSE199939/
      GSE199939_family.xml.tgz
    GSE165816/
      GSE165816_family.xml.tgz
      supplementary_counts/
        GSM5050523_G2counts.csv.gz
        ... the 14 foot-skin files listed in 04_code/configs/M07_full_core_foot_libraries_v1.csv
    primary_evidence/
      M01_remaining_datasets/
        PMC8748704_supplementaryFiles/
          41467_2021_27801_MOESM4_ESM.xlsx
```

The complete expected path, filename, size, source URL when recorded, and SHA-256 inventory is in `03_data/metadata/SOURCE_FILE_MANIFEST.csv`. Legacy machine-local source locations were removed from the public copy; public URLs and identity hashes were retained.

For GSE165816, the 14-library core manifest is authoritative for the supporting analysis. Forearm and peripheral-blood libraries are excluded. For GSE199939, public files may be retained for background inspection, but the series must not enter the core DFU analysis.

