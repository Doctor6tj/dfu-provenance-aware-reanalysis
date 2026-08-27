#!/usr/bin/env python3
"""Deterministic participant- and role-level audit for the remaining M01 datasets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import stat
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


NS = {"m": "http://www.ncbi.nlm.nih.gov/geo/info/MINiML"}
SCHEMA_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_read_only(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_READONLY", 1))


def verify_source_manifest(path: Path, project_root: Path) -> dict:
    failures: list[str] = []
    rows = load_csv(path)
    for row in rows:
        source = project_root / row["path"]
        if not source.exists():
            failures.append(f"MISSING:{row['source_object_id']}")
            continue
        if source.stat().st_size != int(row["bytes"]):
            failures.append(f"SIZE_MISMATCH:{row['source_object_id']}")
        if sha256_file(source) != row["sha256"].casefold():
            failures.append(f"HASH_MISMATCH:{row['source_object_id']}")
        if not is_read_only(source):
            failures.append(f"NOT_READ_ONLY:{row['source_object_id']}")
    return {
        "manifest_path": str(path),
        "source_object_count": len(rows),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def text(node: ET.Element | None) -> str:
    return "" if node is None else " ".join("".join(node.itertext()).split())


def parse_miniml_tgz(path: Path) -> dict:
    with tarfile.open(path, "r:gz") as archive:
        members = [item for item in archive.getmembers() if item.name.endswith("_family.xml")]
        if len(members) != 1:
            raise ValueError(f"Expected one MINiML XML member in {path}; found {len(members)}")
        stream = archive.extractfile(members[0])
        if stream is None:
            raise ValueError(f"Cannot read MINiML XML from {path}")
        root = ET.fromstring(stream.read())

    series = root.find("m:Series", NS)
    if series is None:
        raise ValueError(f"No Series node in {path}")
    samples: list[dict] = []
    for sample in root.findall("m:Sample", NS):
        characteristics = {}
        for node in sample.findall("m:Channel/m:Characteristics", NS):
            characteristics[node.attrib.get("tag", "unlabeled").strip().casefold()] = text(node)
        relations = {
            node.attrib.get("type", ""): node.attrib.get("target", "")
            for node in sample.findall("m:Relation", NS)
        }
        samples.append(
            {
                "gsm_accession": text(sample.find("m:Accession", NS)),
                "title": text(sample.find("m:Title", NS)),
                "source_name": text(sample.find("m:Channel/m:Source", NS)),
                "characteristics": characteristics,
                "relations": relations,
            }
        )
    return {
        "series_accession": text(series.find("m:Accession", NS)),
        "series_title": text(series.find("m:Title", NS)),
        "series_summary": text(series.find("m:Summary", NS)),
        "overall_design": text(series.find("m:Overall-Design", NS)),
        "samples": samples,
    }


def gse134431_identity(sample: dict) -> dict:
    title_value = sample["title"]
    characteristics = sample["characteristics"]
    ulcer_or_skin = characteristics.get("ulcer_or_skin", "")
    outcome = characteristics.get("healer_or_nonhealer", "")
    if ulcer_or_skin.casefold() == "skin":
        match = re.search(r"Donor #(\d+)", title_value, re.I)
        if not match:
            raise ValueError(f"Unparsed GSE134431 skin title: {title_value}")
        number = int(match.group(1))
        return {
            "source_sample_alias": f"DFS{number}",
            "participant_alias": f"GSE134431_DFS_{number:03d}",
            "biological_group": "DIABETIC_FOOT_SKIN_NONULCERATED",
            "tissue_context": "DIABETIC_FOOT_SKIN_NONULCERATED",
            "visit_or_timepoint": "NOT_APPLICABLE",
            "downstream_role": "DIABETIC_FOOT_SKIN_CONTEXT",
            "include_in_primary_module": "FALSE",
            "uncertainty_flag": "POSSIBLE_CROSS_CONTEXT_PARTICIPANT_31" if number == 31 else "NONE",
        }

    um = re.search(r"UM#(\d+)(W\d+)", title_value, re.I)
    p2 = re.search(r"P2#(\d+)", title_value, re.I)
    if not um and not p2:
        raise ValueError(f"Unparsed GSE134431 ulcer title: {title_value}")
    if um:
        number = int(um.group(1))
        source_alias = f"UM{number}{um.group(2).upper()}"
        participant_alias = f"GSE134431_UM_{number:03d}"
        timepoint = um.group(2).upper()
        uncertainty = "POSSIBLE_CROSS_CONTEXT_PARTICIPANT_31" if number == 31 else "NONE"
    else:
        number = int(p2.group(1))
        source_alias = f"P2_{number:03d}"
        participant_alias = f"GSE134431_P2_{number:03d}"
        timepoint = "NOT_PUBLIC"
        uncertainty = "NONE"
    if outcome.casefold() == "healer":
        group = "DFU_HEALER"
    elif outcome.casefold() == "nonhealer":
        group = "DFU_NONHEALER"
    else:
        raise ValueError(f"Unexpected GSE134431 outcome: {outcome}")
    return {
        "source_sample_alias": source_alias,
        "participant_alias": participant_alias,
        "biological_group": group,
        "tissue_context": "DFU_ULCER_EDGE_FULL_THICKNESS",
        "visit_or_timepoint": timepoint,
        "downstream_role": "PRIMARY_HEALING_OUTCOME_CANDIDATE",
        "include_in_primary_module": "TRUE",
        "uncertainty_flag": uncertainty,
    }


def gse143735_identity(sample: dict) -> dict:
    match = re.search(r"(X\d+)_s", sample["title"], re.I)
    if not match:
        raise ValueError(f"Unparsed GSE143735 title: {sample['title']}")
    group_source = sample["characteristics"].get("group", "").casefold()
    if "no ulcer" in group_source:
        group = "DIABETES_NO_DFU"
    elif "non healer" in group_source:
        group = "DFU_NONHEALER_SYSTEMIC_SITE"
    elif "healer" in group_source:
        group = "DFU_HEALER_SYSTEMIC_SITE"
    else:
        raise ValueError(f"Unexpected GSE143735 group: {group_source}")
    alias = match.group(1).upper()
    return {
        "source_sample_alias": alias,
        "participant_alias": f"GSE143735_{alias}",
        "biological_group": group,
        "tissue_context": "FOREARM_WHOLE_SKIN_NONULCERATED",
        "visit_or_timepoint": "BASELINE",
        "downstream_role": "SYSTEMIC_NONULCERATED_FOREARM_CONTEXT_ONLY",
        "include_in_primary_module": "FALSE",
        "uncertainty_flag": "NONE",
    }


def gse199939_identity(sample: dict) -> dict:
    match = re.search(r"\[([^]]+)\]", sample["title"])
    if not match:
        raise ValueError(f"Unparsed GSE199939 title: {sample['title']}")
    alias = match.group(1).upper()
    disease = sample["characteristics"].get("disease", "").casefold()
    if disease == "diabetes":
        group = "DIABETIC_FOOT_SKIN_ULCER_STATUS_UNVERIFIED"
        uncertainty = "SERIES_ASSERTS_DFU_BUT_SAMPLE_METADATA_DO_NOT_ANNOTATE_ULCER"
    elif disease == "non-diabetic":
        group = "NONDIABETIC_FOOT_SKIN"
        uncertainty = "NONE"
    else:
        raise ValueError(f"Unexpected GSE199939 disease: {disease}")
    return {
        "source_sample_alias": alias,
        "participant_alias": f"GSE199939_{alias}",
        "biological_group": group,
        "tissue_context": "FOOT_SKIN; ULCER_STATUS_NOT_SAMPLE_LEVEL_ANNOTATED",
        "visit_or_timepoint": "NOT_PUBLIC",
        "downstream_role": "QUARANTINE_PENDING_AUTHOR_ROLE_DECISION",
        "include_in_primary_module": "FALSE",
        "uncertainty_flag": uncertainty,
    }


def gse165816_identity(sample: dict, mapping: dict[str, dict[str, str]]) -> dict:
    match = re.match(r"(G\d+A?):", sample["title"], re.I)
    if not match:
        raise ValueError(f"Unparsed GSE165816 title: {sample['title']}")
    sample_id = match.group(1).upper()
    if sample_id not in mapping:
        raise ValueError(f"GSE165816 sample {sample_id} missing from supplementary participant map")
    mapped = mapping[sample_id]
    disease = sample["characteristics"].get("disease", "")
    disease_groups = {
        "DFU-healer": "DFU_HEALER",
        "DFU-nonhealer": "DFU_NONHEALER",
        "Non-DFU Diabetic": "DIABETES_NO_DFU",
        "Non-diabetic": "HEALTHY_NONDIABETIC",
    }
    group = disease_groups.get(disease)
    if group != mapped["group_normalized"]:
        raise ValueError(f"GSE165816 group mismatch for {sample_id}: GEO={group}; supplement={mapped['group_normalized']}")
    geo_tissue = sample["characteristics"].get("tissue", "").casefold()
    supplement_tissue = mapped["tissue_context_from_supplement"]
    expected_tissue = {"foot skin": "FOOT_SKIN", "forearm skin": "FOREARM_SKIN", "pbmcs": "PBMC"}.get(geo_tissue)
    if expected_tissue != supplement_tissue:
        raise ValueError(f"GSE165816 tissue mismatch for {sample_id}: GEO={geo_tissue}; supplement={supplement_tissue}")
    if expected_tissue == "FOOT_SKIN" and group.startswith("DFU_"):
        tissue_context = "DFU_SURGICAL_RESECTION_FOOT_WOUND_OR_PERIWOUND; LIBRARY_SUBSITE_NOT_PUBLIC"
    elif expected_tissue == "FOOT_SKIN":
        tissue_context = "NONULCERATED_FOOT_SKIN"
    elif expected_tissue == "FOREARM_SKIN":
        tissue_context = "FOREARM_SKIN_NONULCERATED"
    else:
        tissue_context = "PBMC"
    return {
        "source_sample_alias": sample_id,
        "participant_alias": mapped["participant_alias"],
        "biological_group": group,
        "tissue_context": tissue_context,
        "visit_or_timepoint": "SURGERY_BASELINE",
        "downstream_role": "PARTICIPANT_AWARE_SINGLE_CELL_VALUE_ADD",
        "include_in_primary_module": "FALSE",
        "uncertainty_flag": "MULTIPLE_LIBRARIES_PER_PARTICIPANT_NOT_INDEPENDENT",
    }


def make_sample_rows(datasets: dict[str, dict], gse165816_mapping: dict[str, dict[str, str]]) -> list[dict]:
    rows: list[dict] = []
    identity_functions = {
        "GSE134431": lambda sample: gse134431_identity(sample),
        "GSE143735": lambda sample: gse143735_identity(sample),
        "GSE199939": lambda sample: gse199939_identity(sample),
        "GSE165816": lambda sample: gse165816_identity(sample, gse165816_mapping),
    }
    for dataset_id in sorted(datasets):
        metadata = datasets[dataset_id]
        for sample in metadata["samples"]:
            identity = identity_functions[dataset_id](sample)
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "gsm_accession": sample["gsm_accession"],
                    "sample_title": sample["title"],
                    "source_name": sample["source_name"],
                    **identity,
                    "participant_mapping_status": "SOURCE_ALIAS_OR_SUPPLEMENT_LINKAGE; NOT_A_PUBLIC_CLINICAL_IDENTIFIER",
                    "independence_unit": identity["participant_alias"],
                    "within_participant_sample_count": 0,
                    "evidence_basis": "GEO_MINIML_PRIMARY_METADATA" + ("|PRIMARY_PUBLICATION_SUPPLEMENT" if dataset_id == "GSE165816" else ""),
                }
            )
    counts = Counter((row["dataset_id"], row["participant_alias"]) for row in rows)
    for row in rows:
        row["within_participant_sample_count"] = counts[(row["dataset_id"], row["participant_alias"])]
    return sorted(rows, key=lambda row: (row["dataset_id"], row["gsm_accession"]))


def build_role_decisions(datasets: dict[str, dict], sample_rows: list[dict]) -> dict:
    by_dataset = {dataset_id: [row for row in sample_rows if row["dataset_id"] == dataset_id] for dataset_id in datasets}
    counts = {}
    for dataset_id, rows in by_dataset.items():
        participant_groups: dict[str, str] = {}
        for row in rows:
            participant = row["participant_alias"]
            group = row["biological_group"]
            if participant in participant_groups and participant_groups[participant] != group:
                raise ValueError(f"Participant {participant} spans conflicting groups")
            participant_groups[participant] = group
        counts[dataset_id] = {
            "sample_accessions": len(rows),
            "conservative_participant_units": len(participant_groups),
            "sample_biological_groups": dict(sorted(Counter(row["biological_group"] for row in rows).items())),
            "participant_biological_groups": dict(sorted(Counter(participant_groups.values()).items())),
        }
    counts["GSE134431"]["possible_participant_units_if_numeric_31_link_is_real"] = 20
    counts["GSE165816"]["max_libraries_per_participant"] = max(
        row["within_participant_sample_count"] for row in by_dataset["GSE165816"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_status": "PASS_WITH_GSE199939_AUTHOR_DECISION_PENDING",
        "datasets": {
            "GSE134431": {
                "role": "PRIMARY_HEALING_OUTCOME_BULK_CANDIDATE",
                "defensible_contrast": "DFU_HEALER versus DFU_NONHEALER (7 versus 6 participants)",
                "comparator_boundary": "Eight nonulcerated diabetic foot-skin samples are contextual comparators, not healing-outcome controls.",
                "independence_boundary": "One public RNA-seq sample per DFU participant. Donor #31 and UM#31W4 remain a suspected cross-context linkage only; use 21 conservative units and report a possible minimum of 20.",
                "decision": "INCLUDE_FOR_PARTICIPANT_LEVEL_BULK_HEALING_ANALYSIS",
            },
            "GSE143735": {
                "role": "SYSTEMIC_NONULCERATED_FOREARM_CONTEXT_ONLY",
                "defensible_contrast": "Forearm skin from DFU healers versus nonhealers versus diabetes without ulcer.",
                "comparator_boundary": "All biopsies are nonulcerated forearm whole skin; this cannot validate a local DFU-ulcer tissue signature.",
                "independence_boundary": "13 samples map to 13 source participant aliases; Supplementary Table 5 has concordant 4/5/4 group counts.",
                "decision": "CONTEXT_ONLY_NOT_IN_LOCAL_DFU_META_ANALYSIS",
            },
            "GSE199939": {
                "role": "BIOLOGICAL_LABEL_CONTRADICTION_HOLD",
                "defensible_contrast": "Diabetic foot skin versus non-diabetic foot skin at sample-metadata level.",
                "comparator_boundary": "Series, BioProject, and publication call the diabetic group DFU; all 21 sample and BioSample records annotate only foot skin and diabetes status, with no ulcer field.",
                "independence_boundary": "21 unique donor aliases and one sample per alias; participant independence is defensible, ulcer-tissue identity is not sample-level verifiable.",
                "decision": "QUARANTINE_FROM_CORE; PROPOSE_CONTEXT_OR_SENSITIVITY_ONLY; AUTHOR_CONFIRMATION_REQUIRED",
            },
            "GSE165816": {
                "role": "PARTICIPANT_AWARE_SINGLE_CELL_VALUE_ADD",
                "defensible_contrast": "DFU healer versus nonhealer with diabetes-no-DFU and healthy comparators, stratified by tissue.",
                "comparator_boundary": "Foot, forearm, and PBMC libraries are different biological compartments and must never be pooled as exchangeable samples.",
                "independence_boundary": "The primary supplement maps all 54 public libraries to 27 participants: 7 DFU healers, 4 nonhealers, 6 diabetes-no-DFU, and 10 healthy participants.",
                "decision": "OPTIONAL_VALUE_ADD_WITH_PARTICIPANT_CLUSTERING_OR_PARTICIPANT_LEVEL_AGGREGATION",
            },
        },
        "counts": counts,
        "author_decisions_required": [
            {
                "decision_id": "M01_DEC_GSE199939_ROLE",
                "question": "Approve quarantining GSE199939 from core DFU analyses and retaining it only as diabetic-foot-skin context or a separately labeled sensitivity analysis?",
                "recommended_choice": "APPROVE_QUARANTINE_AND_CONTEXT_ONLY",
                "reason": "Ulcer status is asserted at series/publication level but absent from every sample-level and BioSample tissue/disease field.",
            }
        ],
    }


def audit(args: argparse.Namespace) -> dict:
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = Path(args.gse165816_participant_map).resolve()
    mapping_rows = load_csv(mapping_path)
    mapping = {row["sample_id"].upper(): row for row in mapping_rows}
    if len(mapping_rows) != 54 or len(mapping) != 54:
        raise ValueError("GSE165816 participant map must contain 54 unique sample IDs")

    source_manifest_path = Path(args.source_manifest).resolve()
    source_check = verify_source_manifest(source_manifest_path, project_root)
    family_paths = {
        "GSE134431": Path(args.gse134431_family).resolve(),
        "GSE143735": Path(args.gse143735_family).resolve(),
        "GSE199939": Path(args.gse199939_family).resolve(),
        "GSE165816": Path(args.gse165816_family).resolve(),
    }
    datasets = {dataset_id: parse_miniml_tgz(path) for dataset_id, path in family_paths.items()}
    sample_rows = make_sample_rows(datasets, mapping)
    decisions = build_role_decisions(datasets, sample_rows)

    sample_counts = Counter(row["dataset_id"] for row in sample_rows)
    group_counts = {
        dataset_id: Counter(row["biological_group"] for row in sample_rows if row["dataset_id"] == dataset_id)
        for dataset_id in datasets
    }
    checks = {
        "primary_evidence_hashes_and_readonly": source_check["status"] == "PASS",
        "total_sample_rows_109": len(sample_rows) == 109,
        "dataset_sample_counts": sample_counts == {"GSE134431": 21, "GSE143735": 13, "GSE199939": 21, "GSE165816": 54},
        "gse134431_group_counts": group_counts["GSE134431"] == {"DIABETIC_FOOT_SKIN_NONULCERATED": 8, "DFU_HEALER": 7, "DFU_NONHEALER": 6},
        "gse143735_group_counts": group_counts["GSE143735"] == {"DIABETES_NO_DFU": 4, "DFU_HEALER_SYSTEMIC_SITE": 5, "DFU_NONHEALER_SYSTEMIC_SITE": 4},
        "gse199939_group_counts": group_counts["GSE199939"] == {"DIABETIC_FOOT_SKIN_ULCER_STATUS_UNVERIFIED": 10, "NONDIABETIC_FOOT_SKIN": 11},
        "gse165816_group_counts": group_counts["GSE165816"] == {"DFU_HEALER": 15, "DFU_NONHEALER": 9, "DIABETES_NO_DFU": 12, "HEALTHY_NONDIABETIC": 18},
        "gse165816_27_participants": len({row["participant_alias"] for row in sample_rows if row["dataset_id"] == "GSE165816"}) == 27,
        "gse165816_participant_group_counts": Counter(
            {
                row["participant_alias"]: row["biological_group"]
                for row in sample_rows
                if row["dataset_id"] == "GSE165816"
            }.values()
        ) == {"DFU_HEALER": 7, "DFU_NONHEALER": 4, "DIABETES_NO_DFU": 6, "HEALTHY_NONDIABETIC": 10},
        "gse199939_series_asserts_dfu": "dfu" in datasets["GSE199939"]["series_summary"].casefold(),
        "gse199939_samples_lack_ulcer_annotation": all(
            "ulcer" not in (sample["source_name"] + " " + " ".join(sample["characteristics"].values())).casefold()
            for sample in datasets["GSE199939"]["samples"]
        ),
        "unique_gsm_accessions": len({row["gsm_accession"] for row in sample_rows}) == len(sample_rows),
    }
    qc_status = "PASS_WITH_DECLARED_GSE199939_HOLD" if all(checks.values()) else "FAIL"

    sample_path = output_dir / "remaining_dataset_sample_registry.csv"
    enriched_map_path = output_dir / "gse165816_participant_sample_map.csv"
    decisions_path = output_dir / "remaining_dataset_role_decisions.json"
    qc_path = output_dir / "M01_REMAINING_DATASET_QC.json"
    lock_path = output_dir / "M01_REMAINING_RESULT_LOCK_v1.json"
    write_csv(
        sample_path,
        [
            "dataset_id", "gsm_accession", "sample_title", "source_name", "source_sample_alias",
            "biological_group", "tissue_context", "participant_alias", "participant_mapping_status",
            "visit_or_timepoint", "within_participant_sample_count", "independence_unit", "downstream_role",
            "include_in_primary_module", "uncertainty_flag", "evidence_basis",
        ],
        sample_rows,
    )
    gse165816_rows = [row for row in sample_rows if row["dataset_id"] == "GSE165816"]
    write_csv(
        enriched_map_path,
        [
            "dataset_id", "gsm_accession", "source_sample_alias", "sample_title", "biological_group",
            "tissue_context", "participant_alias", "within_participant_sample_count", "independence_unit",
            "uncertainty_flag", "evidence_basis",
        ],
        gse165816_rows,
    )
    write_json(decisions_path, decisions)
    qc_payload = {
        "schema_version": SCHEMA_VERSION,
        "module_id": "M01_PROVENANCE_AUDIT",
        "audit_scope": ["GSE134431", "GSE143735", "GSE199939", "GSE165816"],
        "status": qc_status,
        "checks": checks,
        "source_verification": source_check,
        "warnings": [
            "GSE134431 donor #31 and UM#31W4 are not merged because public participant linkage is not explicit.",
            "GSE199939 remains quarantined because ulcer identity is not encoded at sample or BioSample level.",
            "GSE165816 library rows are not participant-independent and require participant-aware downstream analysis.",
        ],
        "expression_analysis_performed": False,
    }
    write_json(qc_path, qc_payload)
    supplement_summary_path = mapping_path.with_name("gse165816_supplement_participant_map_summary.json")
    result_files = [mapping_path, sample_path, enriched_map_path, decisions_path, qc_path]
    if supplement_summary_path.exists():
        result_files.insert(1, supplement_summary_path)
    lock_payload = {
        "schema_version": SCHEMA_VERSION,
        "lock_id": "L5C_M01_REMAINING_DATASET_AUDIT_v1",
        "module_id": "M01_PROVENANCE_AUDIT",
        "result_status": qc_status,
        "scientific_boundary": "Metadata, provenance, participant/sample linkage, and dataset-role adjudication only; no expression analysis was run.",
        "input_hashes": {
            "primary_evidence_manifest": sha256_file(source_manifest_path),
            "gse165816_supplement_mapping": sha256_file(mapping_path),
            **{f"{dataset_id}_family": sha256_file(path) for dataset_id, path in family_paths.items()},
        },
        "result_objects": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in result_files
        ],
        "open_author_decision": "M01_DEC_GSE199939_ROLE",
        "recommended_decision": "QUARANTINE_FROM_CORE_AND_RETAIN_AS_CONTEXT_OR_SEPARATE_SENSITIVITY",
    }
    write_json(lock_path, lock_payload)
    if qc_status == "FAIL":
        raise RuntimeError(json.dumps(qc_payload, ensure_ascii=False))
    return {"status": qc_status, "sample_rows": len(sample_rows), "output_dir": str(output_dir)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--gse134431-family", required=True)
    parser.add_argument("--gse143735-family", required=True)
    parser.add_argument("--gse199939-family", required=True)
    parser.add_argument("--gse165816-family", required=True)
    parser.add_argument("--gse165816-participant-map", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


if __name__ == "__main__":
    result = audit(build_parser().parse_args())
    print(json.dumps(result, ensure_ascii=False))
