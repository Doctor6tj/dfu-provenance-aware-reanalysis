#!/usr/bin/env python3
"""Build the M02 provenance-aware cohort harmonization interfaces.

This script consumes only accepted M01 metadata interfaces. It preserves all
public accession rows, collapses analytic independence through locked aliases
and participant mappings, assigns comparator/tissue/role eligibility, and emits
deterministic accession-level, participant-level, and contrast-rule interfaces.
It performs no expression-level analysis and refuses to overwrite outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACCESSION_FIELDS = [
    "dataset_id", "gsm_accession", "source_sample_alias", "sample_title",
    "participant_unit_id", "participant_mapping_status", "biological_group",
    "dfu_status_class", "healing_status_class", "tissue_context_source",
    "tissue_compartment", "tissue_locality_class", "comparator_class",
    "within_participant_accession_count", "accession_alias_group",
    "exact_duplicate_status", "module_role", "primary_contrast_family",
    "eligible_for_primary_compatible_contrast", "eligible_for_declared_secondary_module",
    "sensitivity_only", "core_exclusion_reason", "uncertainty_flag",
    "source_interface",
]

PARTICIPANT_FIELDS = [
    "participant_unit_id", "dataset_ids", "biological_groups", "dfu_status_classes",
    "healing_status_classes", "tissue_compartments", "tissue_locality_classes",
    "gsm_accessions", "accession_row_count", "unique_sample_object_count",
    "primary_eligible_accession_count", "secondary_eligible_accession_count",
    "participant_role", "uncertainty_flags", "mapping_authorities",
]

COMPARATOR_FIELDS = [
    "contrast_id", "dataset_id", "case_group", "comparator_group",
    "tissue_boundary", "analysis_role", "compatibility", "participant_rule",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_new(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite output: {path}")
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json_new(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def classify_group(group: str) -> tuple[str, str, str]:
    if "NONHEALER" in group:
        healing = "NONHEALER"
    elif "HEALER" in group:
        healing = "HEALER"
    else:
        healing = "NOT_APPLICABLE"

    if group in {"DFU_ULCER", "DFU_HEALER", "DFU_NONHEALER", "DFU_HEALER_SYSTEMIC_SITE", "DFU_NONHEALER_SYSTEMIC_SITE"}:
        dfu = "DFU_PRESENT"
    elif group == "DIABETIC_FOOT_SKIN_ULCER_STATUS_UNVERIFIED":
        dfu = "ULCER_STATUS_UNVERIFIED"
    elif group in {"DFS_NONULCERATED_DIABETIC", "DIABETIC_FOOT_SKIN_NONULCERATED", "DIABETES_NO_DFU"}:
        dfu = "DIABETES_WITHOUT_VERIFIED_CURRENT_DFU"
    elif group in {"NFS_HEALTHY_NONDIABETIC", "HEALTHY_NONDIABETIC", "NONDIABETIC_FOOT_SKIN"}:
        dfu = "NO_DFU_NONDIABETIC"
    else:
        raise ValueError(f"Unmapped biological group: {group}")

    comparator = {
        "DFU_ULCER": "CASE_DFU_ULCER",
        "DFS_NONULCERATED_DIABETIC": "CONTROL_DIABETIC_NONULCERATED_FOOT_SKIN",
        "NFS_HEALTHY_NONDIABETIC": "CONTROL_HEALTHY_NONDIABETIC_FOOT_SKIN",
        "DFU_HEALER": "DFU_HEALER",
        "DFU_NONHEALER": "DFU_NONHEALER",
        "DFU_HEALER_SYSTEMIC_SITE": "DFU_HEALER_SYSTEMIC_SITE",
        "DFU_NONHEALER_SYSTEMIC_SITE": "DFU_NONHEALER_SYSTEMIC_SITE",
        "DIABETIC_FOOT_SKIN_NONULCERATED": "DIABETIC_FOOT_SKIN_CONTEXT",
        "DIABETES_NO_DFU": "DIABETES_NO_DFU",
        "DIABETIC_FOOT_SKIN_ULCER_STATUS_UNVERIFIED": "DIABETIC_FOOT_SKIN_ULCER_STATUS_UNVERIFIED",
        "NONDIABETIC_FOOT_SKIN": "NONDIABETIC_FOOT_SKIN",
        "HEALTHY_NONDIABETIC": "HEALTHY_NONDIABETIC",
    }[group]
    return dfu, healing, comparator


def classify_tissue(tissue: str) -> tuple[str, str]:
    upper = tissue.upper()
    if "PBMC" in upper:
        return "PBMC", "SYSTEMIC_BLOOD"
    if "FOREARM" in upper:
        return "FOREARM_SKIN", "SYSTEMIC_FOREARM"
    if any(token in upper for token in ("FOOT", "DFU", "ULCER", "WOUND")):
        return "FOOT_SKIN", "LOCAL_FOOT"
    raise ValueError(f"Unmapped tissue context: {tissue}")


def role_for_row(dataset: str, group: str, is_pair_interface: bool) -> tuple[str, str, bool, bool, bool, str]:
    if is_pair_interface:
        if dataset == "GSE68183":
            return "PROVENANCE_ALIAS_SOURCE_ONLY", "GSE80178_DFU_VS_SEPARATE_DFS_NFS", False, False, False, "EXACT_ALIAS_RETAINED_ONLY_FOR_PROVENANCE"
        return "PRIMARY_DFU_COMPARATOR_DECOMPOSITION", "GSE80178_DFU_VS_SEPARATE_DFS_NFS", True, False, False, ""
    if dataset == "GSE134431":
        if group in {"DFU_HEALER", "DFU_NONHEALER"}:
            return "SECONDARY_HEALING_OUTCOME", "GSE134431_HEALER_VS_NONHEALER", False, True, False, ""
        return "DIABETIC_FOOT_SKIN_CONTEXT", "NONE", False, False, False, "CONTEXT_ONLY"
    if dataset == "GSE143735":
        return "SYSTEMIC_FOREARM_CONTEXT_ONLY", "GSE143735_SYSTEMIC_HEALING_CONTEXT", False, True, False, "NOT_LOCAL_DFU_TISSUE"
    if dataset == "GSE199939":
        return "BACKGROUND_OR_SEPARATELY_LABELLED_SENSITIVITY", "GSE199939_DIABETIC_VS_NONDIABETIC_FOOT_SKIN", False, True, True, "AUTHOR_APPROVED_EXCLUSION_FROM_CORE"
    if dataset == "GSE165816":
        return "PARTICIPANT_AWARE_SINGLE_CELL_VALUE_ADD", "GSE165816_PARTICIPANT_AWARE_TISSUE_STRATIFIED", False, True, False, "VALUE_ADD_NOT_PRIMARY_CORE"
    raise ValueError(f"Unmapped dataset: {dataset}")


def transform_pair_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    participant_counts = Counter(row["analytic_independence_unit"] for row in rows)
    result: list[dict[str, str]] = []
    for row in rows:
        group = row["biological_group"]
        dfu, healing, comparator = classify_group(group)
        compartment, locality = classify_tissue(row["tissue_context"])
        role, family, primary, secondary, sensitivity, exclusion = role_for_row(row["dataset_id"], group, True)
        alias_group = row["duplicate_pair_id"] or row["analytic_independence_unit"]
        result.append({
            "dataset_id": row["dataset_id"],
            "gsm_accession": row["gsm_accession"],
            "source_sample_alias": "",
            "sample_title": row["sample_title"],
            "participant_unit_id": row["analytic_independence_unit"],
            "participant_mapping_status": row["participant_mapping_status"],
            "biological_group": group,
            "dfu_status_class": dfu,
            "healing_status_class": healing,
            "tissue_context_source": row["tissue_context"],
            "tissue_compartment": compartment,
            "tissue_locality_class": locality,
            "comparator_class": comparator,
            "within_participant_accession_count": str(participant_counts[row["analytic_independence_unit"]]),
            "accession_alias_group": alias_group,
            "exact_duplicate_status": "EXACT_CROSS_ACCESSION_ALIAS" if row["duplicate_pair_id"] else "NONE",
            "module_role": role,
            "primary_contrast_family": family,
            "eligible_for_primary_compatible_contrast": bool_text(primary),
            "eligible_for_declared_secondary_module": bool_text(secondary),
            "sensitivity_only": bool_text(sensitivity),
            "core_exclusion_reason": exclusion,
            "uncertainty_flag": "PUBLIC_PARTICIPANT_ID_UNAVAILABLE" if "UNAVAILABLE" in row["participant_mapping_status"] else "NONE",
            "source_interface": "M01_METADATA_PARTICIPANT_SAMPLE_MAP",
        })
    return result


def transform_remaining_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        group = row["biological_group"]
        dfu, healing, comparator = classify_group(group)
        compartment, locality = classify_tissue(row["tissue_context"])
        role, family, primary, secondary, sensitivity, exclusion = role_for_row(row["dataset_id"], group, False)
        result.append({
            "dataset_id": row["dataset_id"],
            "gsm_accession": row["gsm_accession"],
            "source_sample_alias": row["source_sample_alias"],
            "sample_title": row["sample_title"],
            "participant_unit_id": row["participant_alias"],
            "participant_mapping_status": row["participant_mapping_status"],
            "biological_group": group,
            "dfu_status_class": dfu,
            "healing_status_class": healing,
            "tissue_context_source": row["tissue_context"],
            "tissue_compartment": compartment,
            "tissue_locality_class": locality,
            "comparator_class": comparator,
            "within_participant_accession_count": row["within_participant_sample_count"],
            "accession_alias_group": row["participant_alias"],
            "exact_duplicate_status": "NONE",
            "module_role": role,
            "primary_contrast_family": family,
            "eligible_for_primary_compatible_contrast": bool_text(primary),
            "eligible_for_declared_secondary_module": bool_text(secondary),
            "sensitivity_only": bool_text(sensitivity),
            "core_exclusion_reason": exclusion,
            "uncertainty_flag": row["uncertainty_flag"],
            "source_interface": "M01_REMAINING_DATASET_SAMPLE_REGISTRY",
        })
    return result


def aggregate_participants(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["participant_unit_id"]].append(row)
    output: list[dict[str, str]] = []
    role_priority = [
        "PRIMARY_DFU_COMPARATOR_DECOMPOSITION",
        "SECONDARY_HEALING_OUTCOME",
        "PARTICIPANT_AWARE_SINGLE_CELL_VALUE_ADD",
        "SYSTEMIC_FOREARM_CONTEXT_ONLY",
        "BACKGROUND_OR_SEPARATELY_LABELLED_SENSITIVITY",
        "DIABETIC_FOOT_SKIN_CONTEXT",
        "PROVENANCE_ALIAS_SOURCE_ONLY",
    ]
    for participant_id in sorted(grouped):
        items = grouped[participant_id]
        roles = {row["module_role"] for row in items}
        participant_role = next(role for role in role_priority if role in roles)
        if all(row["exact_duplicate_status"] == "EXACT_CROSS_ACCESSION_ALIAS" for row in items):
            unique_objects = len({row["accession_alias_group"] for row in items})
        else:
            unique_objects = len({row["gsm_accession"] for row in items})
        def joined(field: str) -> str:
            return "|".join(sorted({row[field] for row in items if row[field] and row[field] != "NONE"})) or "NONE"
        output.append({
            "participant_unit_id": participant_id,
            "dataset_ids": joined("dataset_id"),
            "biological_groups": joined("biological_group"),
            "dfu_status_classes": joined("dfu_status_class"),
            "healing_status_classes": joined("healing_status_class"),
            "tissue_compartments": joined("tissue_compartment"),
            "tissue_locality_classes": joined("tissue_locality_class"),
            "gsm_accessions": "|".join(sorted(row["gsm_accession"] for row in items)),
            "accession_row_count": str(len(items)),
            "unique_sample_object_count": str(unique_objects),
            "primary_eligible_accession_count": str(sum(row["eligible_for_primary_compatible_contrast"] == "TRUE" for row in items)),
            "secondary_eligible_accession_count": str(sum(row["eligible_for_declared_secondary_module"] == "TRUE" for row in items)),
            "participant_role": participant_role,
            "uncertainty_flags": joined("uncertainty_flag"),
            "mapping_authorities": joined("source_interface"),
        })
    return output


def verify_gse165816_interface(remaining: list[dict[str, str]], authoritative: list[dict[str, str]]) -> None:
    remaining_map = {
        row["gsm_accession"]: (row["participant_alias"], row["biological_group"], row["within_participant_sample_count"])
        for row in remaining if row["dataset_id"] == "GSE165816"
    }
    authority_map = {
        row["gsm_accession"]: (row["participant_alias"], row["biological_group"], row["within_participant_sample_count"])
        for row in authoritative
    }
    if remaining_map != authority_map:
        raise RuntimeError("GSE165816 participant mapping mismatch between accepted M01 interfaces")


def build_qc(accession_rows: list[dict[str, str]], participant_rows: list[dict[str, str]], rules: list[dict[str, str]], parameters: dict[str, Any]) -> dict[str, Any]:
    expected = parameters["expected_counts"]
    dataset_counts = Counter(row["dataset_id"] for row in accession_rows)
    gse165816_rows = [row for row in accession_rows if row["dataset_id"] == "GSE165816"]
    gse165816_participants = {row["participant_unit_id"] for row in gse165816_rows}
    alias_groups = {row["accession_alias_group"] for row in accession_rows if row["exact_duplicate_status"] == "EXACT_CROSS_ACCESSION_ALIAS"}
    checks = {
        "accession_rows_127": len(accession_rows) == expected["accession_rows"],
        "unique_gsm_accessions_127": len({row["gsm_accession"] for row in accession_rows}) == expected["unique_gsm_accessions"],
        "analytic_participant_units_94": len(participant_rows) == expected["analytic_participant_units"],
        "dataset_accession_counts": dict(sorted(dataset_counts.items())) == expected["dataset_accession_rows"],
        "shared_exact_alias_pairs_6": len(alias_groups) == expected["shared_exact_alias_pairs"],
        "gse68183_primary_eligible_zero": sum(row["eligible_for_primary_compatible_contrast"] == "TRUE" for row in accession_rows if row["dataset_id"] == "GSE68183") == 0,
        "gse80178_primary_eligible_12": sum(row["eligible_for_primary_compatible_contrast"] == "TRUE" for row in accession_rows if row["dataset_id"] == "GSE80178") == expected["gse80178_deduplicated_primary_rows"],
        "gse199939_primary_eligible_zero": sum(row["eligible_for_primary_compatible_contrast"] == "TRUE" for row in accession_rows if row["dataset_id"] == "GSE199939") == expected["gse199939_core_eligible_rows"],
        "gse199939_all_sensitivity_only": all(row["sensitivity_only"] == "TRUE" for row in accession_rows if row["dataset_id"] == "GSE199939"),
        "gse165816_54_libraries": len(gse165816_rows) == expected["gse165816_libraries"],
        "gse165816_27_participants": len(gse165816_participants) == expected["gse165816_participants"],
        "gse165816_tissues_separate": {row["tissue_compartment"] for row in gse165816_rows} == {"FOOT_SKIN", "FOREARM_SKIN", "PBMC"},
        "comparator_rules_7": len(rules) == 7,
        "required_accession_fields_nonempty": all(all(row[field] != "" for field in ACCESSION_FIELDS if field not in {"source_sample_alias", "core_exclusion_reason"}) for row in accession_rows),
        "no_expression_analysis": parameters["expression_analysis_performed"] is False,
    }
    failed = [name for name, value in checks.items() if not value]
    return {
        "schema_version": "1.0",
        "module_id": "M02_COHORT_HARMONIZATION",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "accession_rows": len(accession_rows),
            "analytic_participant_units": len(participant_rows),
            "dataset_accession_rows": dict(sorted(dataset_counts.items())),
            "shared_exact_alias_pairs": len(alias_groups),
            "gse165816_participants": len(gse165816_participants),
        },
        "expression_analysis_performed": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-map", required=True, type=Path)
    parser.add_argument("--pair-map", required=True, type=Path)
    parser.add_argument("--remaining-registry", required=True, type=Path)
    parser.add_argument("--gse165816-map", required=True, type=Path)
    parser.add_argument("--candidate-registry", required=True, type=Path)
    parser.add_argument("--m01-closeout-lock", required=True, type=Path)
    parser.add_argument("--parameters", required=True, type=Path)
    parser.add_argument("--comparator-rules", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite output directory: {args.output_dir}")
    parameters = json.loads(args.parameters.read_text(encoding="utf-8"))
    rules_config = json.loads(args.comparator_rules.read_text(encoding="utf-8"))
    inputs = {
        "participant_sample_map_candidate": args.participant_map,
        "gse68183_gse80178_pair_adjudication": args.pair_map,
        "remaining_dataset_sample_registry": args.remaining_registry,
        "gse165816_participant_sample_map": args.gse165816_map,
        "candidate_dataset_registry_after_m01_closeout": args.candidate_registry,
        "m01_closeout_result_lock": args.m01_closeout_lock,
    }
    actual_hashes = {name: sha256_file(path) for name, path in inputs.items()}
    if actual_hashes != parameters["input_sha256"]:
        raise RuntimeError(f"Input hash mismatch: expected {parameters['input_sha256']}; found {actual_hashes}")

    pair_rows = read_csv(args.participant_map)
    pair_adjudication = read_csv(args.pair_map)
    remaining_rows = read_csv(args.remaining_registry)
    gse165816_authority = read_csv(args.gse165816_map)
    candidate_rows = read_csv(args.candidate_registry)
    closeout = json.loads(args.m01_closeout_lock.read_text(encoding="utf-8"))
    if len(pair_adjudication) != 6 or not all(row["exact_raw_object_identity"] == "TRUE" for row in pair_adjudication):
        raise RuntimeError("Exact pair adjudication authority is incomplete")
    verify_gse165816_interface(remaining_rows, gse165816_authority)
    candidate = {row["dataset_id"]: row for row in candidate_rows}
    if candidate["GSE199939"]["status"] != "AUTHOR_APPROVED_QUARANTINE_FROM_CORE":
        raise RuntimeError("GSE199939 author-approved quarantine is missing")
    if closeout.get("m02_execution_authorized") is not False:
        raise RuntimeError("Unexpected M01 closeout route")

    accession_rows = transform_pair_rows(pair_rows) + transform_remaining_rows(remaining_rows)
    accession_rows.sort(key=lambda row: (row["dataset_id"], row["gsm_accession"]))
    participant_rows = aggregate_participants(accession_rows)
    rules = rules_config["rules"]
    qc = build_qc(accession_rows, participant_rows, rules, parameters)
    if qc["status"] != "PASS":
        raise RuntimeError(f"M02 interface QC failed: {qc['failed_checks']}")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    accession_path = args.output_dir / "M02_accession_level_manifest.csv"
    participant_path = args.output_dir / "M02_participant_level_manifest.csv"
    comparator_path = args.output_dir / "M02_comparator_compatibility_matrix.csv"
    qc_path = args.output_dir / "M02_INTERFACE_QC.json"
    write_csv_new(accession_path, ACCESSION_FIELDS, accession_rows)
    write_csv_new(participant_path, PARTICIPANT_FIELDS, participant_rows)
    write_csv_new(comparator_path, COMPARATOR_FIELDS, rules)
    write_json_new(qc_path, qc)

    result_objects = {}
    for path in [accession_path, participant_path, comparator_path, qc_path]:
        result_objects[path.name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    lock_candidate = {
        "schema_version": "1.0",
        "module_id": "M02_COHORT_HARMONIZATION",
        "status": "PASS_INTERFACE_CANDIDATE_PENDING_ACCEPTANCE",
        "scientific_boundary": "Metadata and analysis-interface harmonization only; no expression analysis",
        "input_sha256": actual_hashes,
        "code_sha256": sha256_file(Path(__file__).resolve()),
        "parameter_sha256": sha256_file(args.parameters),
        "comparator_rule_sha256": sha256_file(args.comparator_rules),
        "result_objects": result_objects,
        "counts": qc["counts"],
        "next_gate": "G5_M02_QC_AND_LOCK",
        "expression_analysis_performed": False,
    }
    write_json_new(args.output_dir / "M02_INTERFACE_LOCK_CANDIDATE_v1.json", lock_candidate)
    execution_log = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "foreground_execution": True,
        "accession_rows": len(accession_rows),
        "participant_units": len(participant_rows),
        "expression_analysis_performed": False,
    }
    write_json_new(args.output_dir / "M02_execution_log.json", execution_log)
    print(json.dumps(execution_log, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
