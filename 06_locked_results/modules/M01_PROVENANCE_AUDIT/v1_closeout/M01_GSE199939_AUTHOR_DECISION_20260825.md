# GSE199939 Author Decision — 2026-08-25

- Decision ID: `DEC_GSE199939_CONTEXT_ONLY_AUTHOR_APPROVED_20260825`
- Authority: AUTHOR
- Status: APPROVED
- M01 closeout run: `M01_CLOSEOUT_20260825T075100Z`

## Decision

Exclude GSE199939 from the core DFU analysis. Retain it only as diabetic-foot-skin background data or as a separately labelled sensitivity analysis.

## Reason carried forward from the locked audit

The GEO series, BioProject, and publication describe DFU, but the 21 public sample-level GEO and BioSample records document foot skin and diabetes status without a sample-level ulcer field. The author-approved role prevents unverified ulcer-tissue identity from entering the compatible core DFU contrast.

## Downstream requirements

1. Do not include GSE199939 in the core DFU-tissue analysis.
2. If used, label it explicitly as diabetic-foot-skin background or a separate sensitivity analysis.
3. Never pool its result into the primary compatible-contrast synthesis without reopening this author decision on new primary evidence.
4. Preserve the 10 diabetic versus 11 non-diabetic sample accounting and participant-level independence boundary.
