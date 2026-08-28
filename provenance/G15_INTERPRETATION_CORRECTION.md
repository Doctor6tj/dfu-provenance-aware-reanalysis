# G15 interpretation correction

Date: 2026-08-28

## Scope

An external presubmission review identified that the earlier wording “0 of
18,865 genes met the cross-study robustness rule” treated a structurally
unestimable question as a zero count. After provenance correction, only one
independent biologically compatible bulk study remained. The required minimum
was two. Cross-study gene and pathway robustness are therefore **not
estimable**.

## What changed

- Manuscript and public-facing figure language now states “not estimable”.
- The 18,865 value is retained only as the within-GSE80178 tested-gene universe.
- GSE199939 is described as context only; specimen-level ulcer status is
  unresolved in the public metadata.
- The all-12 primary analyses, n=11 targeted sensitivity results, and
  participant-level single-cell numeric results are unchanged.

## Historical files

Original execution locks and QC records are retained unchanged to preserve the
analysis history. Their earlier terms such as `VALID_NULL`, `prespecified`, or
`background` are historical labels and are not the current submission-facing
interpretation. The study was not preregistered; analysis roles and settings
were defined and archived before final statistical runs.
