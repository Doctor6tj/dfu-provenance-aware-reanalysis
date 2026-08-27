#!/usr/bin/env python3
"""Prepare publication-facing supplementary-table payloads from locked DFU sources.

This script performs deterministic column renaming and validation only. It does
not rerun any biological or statistical analysis and never modifies source files.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

TABLES = {
    "ST1": {
        "file": "Supplementary_Table_S1_Exact_Sample_Reuse_v01.csv",
        "title": "Supplementary Table S1. Exact raw-object reuse between GSE68183 and GSE80178",
        "description": "One row per exact reused control object. Accession aliases are collapsed to one conservative analytic unit without inferring an undisclosed real-world participant identifier.",
        "headers": [
            ("pair_id", "Pair ID"),
            ("decompressed_cel_sha256", "Decompressed CEL SHA-256"),
            ("gse68183_gsm", "GSE68183 GSM"),
            ("gse68183_title", "GSE68183 sample title"),
            ("gse68183_group", "GSE68183 group"),
            ("gse80178_gsm", "GSE80178 GSM"),
            ("gse80178_title", "GSE80178 sample title"),
            ("gse80178_group", "GSE80178 group"),
            ("exact_raw_object_identity", "Exact raw-object identity"),
            ("normalized_title_concordant", "Normalized title concordant"),
            ("group_semantics_concordant", "Group semantics concordant"),
            ("analytic_independence_unit", "Conservative analytic unit"),
            ("clinical_participant_identifier_status", "Participant identifier status"),
            ("source_declared_reuse_evidence", "Source-declared reuse evidence"),
            ("adjudication_status", "Adjudication status"),
            ("interpretation_boundary", "Interpretation boundary"),
        ],
    },
    "ST2": {
        "file": "Supplementary_Table_S2_Participant_Sample_Interface_v01.csv",
        "title": "Supplementary Table S2. Participant-aware sample interface across registered datasets",
        "description": "One row per conservative analytic participant/specimen unit, retaining accession counts, unique source objects, analysis eligibility, and uncertainty flags.",
        "headers": [
            ("participant_unit_id", "Analytic participant unit"),
            ("dataset_ids", "Dataset ID(s)"),
            ("biological_groups", "Biological group(s)"),
            ("dfu_status_classes", "DFU status class"),
            ("healing_status_classes", "Healing status class"),
            ("tissue_compartments", "Tissue compartment(s)"),
            ("tissue_locality_classes", "Tissue locality class(es)"),
            ("gsm_accessions", "GSM accession(s)"),
            ("accession_row_count", "Accession rows"),
            ("unique_sample_object_count", "Unique sample objects"),
            ("primary_eligible_accession_count", "Primary-eligible accessions"),
            ("secondary_eligible_accession_count", "Secondary-eligible accessions"),
            ("participant_role", "Participant/sample role"),
            ("uncertainty_flags", "Uncertainty flag(s)"),
            ("mapping_authorities", "Mapping authority"),
        ],
    },
    "ST3": {
        "file": "Supplementary_Table_S3_Dataset_Roles_and_Comparability_v01.csv",
        "title": "Supplementary Table S3. Dataset roles, transformation classes, and comparability boundaries",
        "description": "Prespecified role and quantitative-comparability rules for all six registered GEO series.",
        "headers": [
            ("dataset_id", "Dataset ID"),
            ("platform_or_modality", "Platform / modality"),
            ("tissue_or_compartment", "Tissue / compartment"),
            ("accession_rows", "Accession rows"),
            ("analytic_participant_units", "Analytic participant units"),
            ("analysis_role", "Analysis role"),
            ("independence_unit", "Inferential / independence unit"),
            ("transform_class", "Transformation class"),
            ("cohort_specific_score_name", "Cohort-specific score"),
            ("cross_cohort_quantitative_comparability", "Cross-cohort quantitative comparability"),
            ("primary_use", "Use in current study"),
            ("boundary_or_exclusion", "Boundary / exclusion"),
            ("authority_path", "Authority path"),
            ("status", "Status"),
        ],
    },
    "ST4": {
        "file": "Supplementary_Table_S4_Comparator_Compatibility_v01.csv",
        "title": "Supplementary Table S4. Comparator compatibility, inclusion, sensitivity, and exclusion rules",
        "description": "One row per prespecified contrast or evidence role, including tissue boundary and participant-aware rule.",
        "headers": [
            ("contrast_id", "Contrast ID"),
            ("dataset_id", "Dataset ID"),
            ("case_group", "Case group"),
            ("comparator_group", "Comparator group"),
            ("tissue_boundary", "Tissue boundary"),
            ("analysis_role", "Analysis role"),
            ("compatibility", "Compatibility / disposition"),
            ("participant_rule", "Participant-aware rule"),
        ],
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def publish_rows(rows: list[dict[str, str]], headers: list[tuple[str, str]]) -> list[list[str]]:
    return [[row[key] for key, _ in headers] for row in rows]


def write_csv(path: Path, headers: list[tuple[str, str]], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([label for _, label in headers])
        writer.writerows(rows)


def as_int(value: str) -> int:
    return int(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/supplementary_tables_rebuilt"),
        help="New output directory; existing non-empty directories are refused.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser()
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir = output_dir.resolve()

    sources = {
        "ST1": project_root / "06_locked_results" / "modules" / "M01_PROVENANCE_AUDIT" / "v1_metadata_adjudication" / "gse68183_gse80178_pair_adjudication.csv",
        "ST2": project_root / "06_locked_results" / "modules" / "M02_COHORT_HARMONIZATION" / "v1" / "M02_participant_level_manifest.csv",
        "ST3": project_root / "07_manuscript" / "control_manifests" / "G7_MANUSCRIPT_CONTROL_v1_20260826" / "dataset_role_transform_manifest.csv",
        "ST4": project_root / "06_locked_results" / "modules" / "M02_COHORT_HARMONIZATION" / "v1" / "M02_comparator_compatibility_matrix.csv",
    }

    for source in sources.values():
        if not source.is_file():
            raise FileNotFoundError(source)

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty candidate directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rows = {table_id: read_csv(path) for table_id, path in sources.items()}

    st1 = source_rows["ST1"]
    st2 = source_rows["ST2"]
    st3 = source_rows["ST3"]
    st4 = source_rows["ST4"]

    validations = {
        "ST1_has_6_exact_pairs": len(st1) == 6 and all(row["exact_raw_object_identity"].upper() == "TRUE" for row in st1),
        "ST1_has_6_unique_analytic_units": len({row["analytic_independence_unit"] for row in st1}) == 6,
        "ST2_has_94_analytic_units": len(st2) == 94,
        "ST2_accession_rows_total_127": sum(as_int(row["accession_row_count"]) for row in st2) == 127,
        "ST2_unique_source_objects_total_121": sum(as_int(row["unique_sample_object_count"]) for row in st2) == 121,
        "ST2_GSE165816_has_27_participants_and_54_libraries": (
            len([row for row in st2 if row["dataset_ids"] == "GSE165816"]) == 27
            and sum(as_int(row["accession_row_count"]) for row in st2 if row["dataset_ids"] == "GSE165816") == 54
        ),
        "ST3_has_all_6_registered_datasets": len(st3) == 6 and {row["dataset_id"] for row in st3} == {"GSE68183", "GSE80178", "GSE134431", "GSE143735", "GSE199939", "GSE165816"},
        "ST4_has_7_prespecified_rules": len(st4) == 7,
        "ST4_GSE199939_excluded_from_core": any(row["dataset_id"] == "GSE199939" and row["compatibility"] == "EXCLUDED_FROM_CORE" for row in st4),
    }
    if not all(validations.values()):
        failed = [name for name, passed in validations.items() if not passed]
        raise RuntimeError(f"Supplementary-table source validation failed: {failed}")

    payload_tables = []
    for table_id, spec in TABLES.items():
        published = publish_rows(source_rows[table_id], spec["headers"])
        write_csv(output_dir / spec["file"], spec["headers"], published)
        payload_tables.append(
            {
                "table_id": table_id,
                "title": spec["title"],
                "description": spec["description"],
                "headers": [label for _, label in spec["headers"]],
                "rows": published,
                "source_path": str(sources[table_id].relative_to(project_root)).replace("\\", "/"),
                "csv_path": str((output_dir / spec["file"]).relative_to(project_root)).replace("\\", "/"),
            }
        )

    payload = {
        "schema_version": "1.0",
        "project_id": "DFU_PRR_2026",
        "candidate_id": "G9_SUPPLEMENTARY_TABLES_v01_20260826",
        "scope": "Deterministic publication-facing views of locked sources; no biological or statistical rerun.",
        "lock_context": [
            "L5B_M01_DATASET_RELATIONSHIP_v1",
            "L5E_M02_COHORT_HARMONIZATION_v1",
            "L5_M07_FULL_CORE_POST_RUN_v1",
        ],
        "tables": payload_tables,
        "validations": validations,
    }
    (output_dir / "Supplementary_Tables_payload_v01.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "Supplementary_Tables_QC_v01.json").write_text(
        json.dumps(
            {
                "candidate_id": payload["candidate_id"],
                "status": "PASS",
                "no_analysis_rerun": True,
                "source_row_counts": {key: len(value) for key, value in source_rows.items()},
                "validations": validations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "README.txt").write_text(
        "DFU supplementary provenance tables v01\n"
        "\n"
        "These CSV tables are deterministic publication-facing views of locked M01/M02/G7 authorities.\n"
        "No biological or statistical analysis was rerun. Original and locked files were not modified.\n"
        "The Excel workbook is built separately with the spreadsheet artifact workflow.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "output_dir": str(output_dir), "tables": {k: len(v) for k, v in source_rows.items()}}, indent=2))


if __name__ == "__main__":
    main()
