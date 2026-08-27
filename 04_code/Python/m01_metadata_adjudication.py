#!/usr/bin/env python3
"""Deterministic M01 adjudication of GSE68183/GSE80178 sample reuse and roles."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SCHEMA_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_title(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"\s+gene expression profile$", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def parse_series_matrix(path: Path) -> dict:
    series: dict[str, list[str]] = {}
    sample_rows: dict[str, list[str]] = {}
    characteristic_rows: list[list[str]] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if not row:
                continue
            key, values = row[0], row[1:]
            if key == "!series_matrix_table_begin":
                break
            if key.startswith("!Series_"):
                series.setdefault(key, []).extend(values)
            elif key == "!Sample_characteristics_ch1":
                characteristic_rows.append(values)
            elif key.startswith("!Sample_"):
                sample_rows[key] = values

    accessions = sample_rows.get("!Sample_geo_accession", [])
    if not accessions:
        raise ValueError(f"No sample accessions found in {path}")
    samples: list[dict] = []
    for index, accession in enumerate(accessions):
        characteristics: dict[str, str] = {}
        for values in characteristic_rows:
            value = values[index].strip() if index < len(values) else ""
            if ":" in value:
                key, item = value.split(":", 1)
                characteristics[key.strip().casefold().replace(" ", "_")] = item.strip()
            elif value:
                characteristics[f"unparsed_{len(characteristics) + 1}"] = value
        samples.append(
            {
                "gsm_accession": accession.strip(),
                "title": sample_rows.get("!Sample_title", [""] * len(accessions))[index].strip(),
                "source_name": sample_rows.get("!Sample_source_name_ch1", [""] * len(accessions))[index].strip(),
                "characteristics": characteristics,
            }
        )
    return {"path": str(path), "series": series, "samples": samples}


def classify_group(dataset_id: str, sample: dict) -> str:
    title = sample["title"].casefold()
    tissue = sample["characteristics"].get("tissue", "").casefold()
    disease = sample["characteristics"].get("disease_state", "").casefold()
    if dataset_id == "GSE68183":
        if "non-ulcerated non-neuropathic diabetic" in tissue or (
            "diabetic foot skin" in title and "non-diabetic" not in title
        ):
            return "DFS_NONULCERATED_DIABETIC"
        if "healthy non-diabetic" in tissue or "non-diabetic foot skin" in title:
            return "NFS_HEALTHY_NONDIABETIC"
    if dataset_id == "GSE80178":
        if "foot ulcer" in tissue or "diabetic foot ulcer" in title:
            return "DFU_ULCER"
        if "foot skin" in tissue and disease == "diabetic":
            return "DFS_NONULCERATED_DIABETIC"
        if "foot skin" in tissue and disease == "non-diabetic":
            return "NFS_HEALTHY_NONDIABETIC"
    return "UNRESOLVED"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prepare_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise FileExistsError(f"Output directory must be empty before execution: {path}")


def verify_hash_manifest(path: Path, project_root: Path) -> dict:
    rows = load_rows(path)
    failures: list[str] = []
    for row in rows:
        target = Path(row["path"])
        if not target.is_absolute():
            target = project_root / target
        if not target.exists():
            failures.append(f"MISSING:{row['source_object_id']}")
        elif sha256_file(target) != row["sha256"].casefold():
            failures.append(f"HASH_MISMATCH:{row['source_object_id']}")
    return {"rows": rows, "failures": failures, "status": "PASS" if not failures else "FAIL"}


def publication_evidence_checks(source_rows: list[dict[str, str]], project_root: Path) -> dict[str, bool]:
    by_id = {row["source_object_id"]: row for row in source_rows}
    plos_path = project_root / by_id["M01E_SRC001"]["path"]
    pmc_path = project_root / by_id["M01E_SRC002"]["path"]
    plos_root = ET.parse(plos_path).getroot()
    plos_text = " ".join(text.strip() for text in plos_root.itertext() if text.strip()).casefold()
    pmc_raw = pmc_path.read_text(encoding="utf-8", errors="replace")
    pmc_text = html.unescape(re.sub(r"<[^>]+>", " ", pmc_raw)).casefold()
    pmc_text = " ".join(pmc_text.split())
    return {
        "plos_doi_present": "10.1371/journal.pone.0137133" in plos_text,
        "plos_gse68186_present": "gse68186" in plos_text,
        "plos_dfs_nfs_context_present": "non-neuropathic diabetic" in plos_text and "non-diabetic" in plos_text,
        "pmc_gse68186_control_reuse_present": "gse68186" in pmc_text and "previously published control foot skin" in pmc_text,
        "pmc_both_control_strata_present": "both were used as controls" in pmc_text,
        "pmc_gse80178_present": "gse80178" in pmc_text,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def adjudicate(args: argparse.Namespace) -> dict:
    project_root = Path(args.project_root).resolve()
    p68183 = Path(args.gse68183_matrix).resolve()
    p80178 = Path(args.gse80178_matrix).resolve()
    pilot_matches_path = Path(args.pilot_matches).resolve()
    source_manifest_path = Path(args.primary_source_manifest).resolve()
    evidence_registry_path = Path(args.evidence_registry).resolve()
    output_dir = Path(args.output_dir).resolve()
    prepare_output_dir(output_dir)

    meta68183 = parse_series_matrix(p68183)
    meta80178 = parse_series_matrix(p80178)
    samples68183 = {row["gsm_accession"]: row for row in meta68183["samples"]}
    samples80178 = {row["gsm_accession"]: row for row in meta80178["samples"]}
    matches = sorted(load_rows(pilot_matches_path), key=lambda row: row["gse68183_gsm"])
    evidence_rows = load_rows(evidence_registry_path)
    evidence_ids = {row["evidence_id"] for row in evidence_rows}
    source_check = verify_hash_manifest(source_manifest_path, project_root)
    publication_checks = publication_evidence_checks(source_check["rows"], project_root)

    pair_rows: list[dict] = []
    shared_units: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(matches, start=1):
        left = samples68183[match["gse68183_gsm"]]
        right = samples80178[match["gse80178_gsm"]]
        left_group = classify_group("GSE68183", left)
        right_group = classify_group("GSE80178", right)
        title_match = normalize_title(left["title"]) == normalize_title(right["title"])
        group_match = left_group == right_group and left_group != "UNRESOLVED"
        unit = f"M01_SHARED_FS_{index:03d}"
        pair_id = f"PAIR{index:03d}"
        shared_units[left["gsm_accession"]] = (unit, pair_id)
        shared_units[right["gsm_accession"]] = (unit, pair_id)
        pair_rows.append(
            {
                "pair_id": pair_id,
                "decompressed_cel_sha256": match["decompressed_cel_sha256"],
                "gse68183_gsm": left["gsm_accession"],
                "gse68183_title": left["title"],
                "gse68183_group": left_group,
                "gse80178_gsm": right["gsm_accession"],
                "gse80178_title": right["title"],
                "gse80178_group": right_group,
                "exact_raw_object_identity": "TRUE",
                "normalized_title_concordant": str(title_match).upper(),
                "group_semantics_concordant": str(group_match).upper(),
                "analytic_independence_unit": unit,
                "clinical_participant_identifier_status": "NOT_PUBLIC; SAME_SAMPLE_OBJECT_PAIR",
                "source_declared_reuse_evidence": "EVID004|EVID005|EVID006",
                "adjudication_status": "EXACT_RAW_OBJECT_AND_METADATA_CONCORDANT" if title_match and group_match else "HUMAN_DECISION_REQUIRED",
                "interpretation_boundary": "Collapse accession aliases to one analytic unit; do not infer a real-world participant identifier.",
            }
        )

    participant_rows: list[dict] = []
    dfu_counter = 0
    for dataset_id, metadata in (("GSE68183", meta68183), ("GSE80178", meta80178)):
        for sample in metadata["samples"]:
            gsm = sample["gsm_accession"]
            group = classify_group(dataset_id, sample)
            if gsm in shared_units:
                unit, pair_id = shared_units[gsm]
                mapping_status = "SAME_SAMPLE_OBJECT_ACROSS_ACCESSIONS"
                downstream_role = "CONTROL_SOURCE_CONTEXT" if dataset_id == "GSE68183" else "REUSED_CONTROL_ALIAS_IN_PRIMARY_CONTRAST"
                include = "FALSE" if dataset_id == "GSE68183" else "TRUE"
            else:
                dfu_counter += 1
                unit = f"M01_GSE80178_DFU_{dfu_counter:03d}"
                pair_id = ""
                mapping_status = "ONE_GEO_SAMPLE_PER_SOURCE_REPORTED_SPECIMEN; PUBLIC_PARTICIPANT_ID_UNAVAILABLE"
                downstream_role = "PRIMARY_DFU_SAMPLE"
                include = "TRUE"
            participant_rows.append(
                {
                    "dataset_id": dataset_id,
                    "gsm_accession": gsm,
                    "sample_title": sample["title"],
                    "biological_group": group,
                    "tissue_context": sample["characteristics"].get("tissue", sample["source_name"]),
                    "disease_state": sample["characteristics"].get("disease_state", "SOURCE_DESCRIPTION_ONLY"),
                    "analytic_independence_unit": unit,
                    "duplicate_pair_id": pair_id,
                    "participant_mapping_status": mapping_status,
                    "participant_id_source": "CONSERVATIVE_ANALYTIC_ALIAS_NOT_A_REAL_IDENTIFIER",
                    "downstream_role": downstream_role,
                    "include_once_in_deduplicated_GSE80178_contrast": include,
                }
            )

    counts68183: dict[str, int] = {}
    counts80178: dict[str, int] = {}
    for sample in meta68183["samples"]:
        group = classify_group("GSE68183", sample)
        counts68183[group] = counts68183.get(group, 0) + 1
    for sample in meta80178["samples"]:
        group = classify_group("GSE80178", sample)
        counts80178[group] = counts80178.get(group, 0) + 1

    all_pair_pass = bool(pair_rows) and all(row["adjudication_status"] == "EXACT_RAW_OBJECT_AND_METADATA_CONCORDANT" for row in pair_rows)
    expected_counts = (
        len(meta68183["samples"]) == 6
        and counts68183 == {"DFS_NONULCERATED_DIABETIC": 3, "NFS_HEALTHY_NONDIABETIC": 3}
        and len(meta80178["samples"]) == 12
        and counts80178 == {"DFU_ULCER": 6, "DFS_NONULCERATED_DIABETIC": 3, "NFS_HEALTHY_NONDIABETIC": 3}
    )
    evidence_complete = {"EVID001", "EVID002", "EVID003", "EVID004", "EVID005", "EVID006"}.issubset(evidence_ids)
    unique_units = len({row["analytic_independence_unit"] for row in participant_rows})
    qc_pass = (
        source_check["status"] == "PASS"
        and all(publication_checks.values())
        and len(matches) == 6
        and all_pair_pass
        and expected_counts
        and evidence_complete
        and len(participant_rows) == 18
        and unique_units == 12
    )

    pair_fields = list(pair_rows[0].keys())
    participant_fields = list(participant_rows[0].keys())
    write_csv(output_dir / "gse68183_gse80178_pair_adjudication.csv", pair_fields, pair_rows)
    write_csv(output_dir / "participant_sample_map_candidate.csv", participant_fields, participant_rows)

    decision = {
        "schema_version": SCHEMA_VERSION,
        "module_id": "M01_PROVENANCE_AUDIT",
        "decision_id": "M01_GSE68183_GSE80178_RELATIONSHIP_v1",
        "verdict": "PASS" if qc_pass else "HUMAN_DECISION_REQUIRED",
        "relationship": "GSE80178 contains six new DFU samples and reuses the six earlier GSE68183/GSE68186 foot-skin control sample objects.",
        "dataset_roles": {
            "GSE80178": "PRIMARY_DFU_VERSUS_FOOT_SKIN_CONTRAST_CONTAINER; 6 DFU plus 6 reused controls",
            "GSE68183": "COMPARATOR_CONTEXT_AND_CONTROL_SOURCE; 3 DFS versus 3 NFS; not an independent DFU validation cohort",
        },
        "allowed_uses": [
            "Use each exact shared raw sample object once in any deduplicated analysis.",
            "Retain DFS and NFS as explicit comparator strata.",
            "Evaluate the source-published pooled foot-skin comparator only as a declared compatible-contrast or sensitivity specification.",
        ],
        "forbidden_uses": [
            "Treat GSE68183 as an independent validation cohort for GSE80178.",
            "Relabel non-ulcerated GSE68183 foot skin as DFU tissue.",
            "Count accession aliases as separate participants or samples.",
        ],
        "evidence_ids": sorted(evidence_ids),
        "participant_boundary": "Public sources do not expose real participant identifiers for the six control samples; exact accession pairs share one conservative analytic independence unit.",
    }
    (output_dir / "dataset_relationship_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    qc = {
        "schema_version": SCHEMA_VERSION,
        "module_id": "M01_PROVENANCE_AUDIT",
        "run_type": "PRIMARY_METADATA_ADJUDICATION",
        "verdict": "PASS" if qc_pass else "HUMAN_DECISION_REQUIRED",
        "input_hashes": {
            p68183.name: sha256_file(p68183),
            p80178.name: sha256_file(p80178),
            pilot_matches_path.name: sha256_file(pilot_matches_path),
            source_manifest_path.name: sha256_file(source_manifest_path),
            evidence_registry_path.name: sha256_file(evidence_registry_path),
        },
        "source_hash_check": source_check,
        "publication_evidence_checks": publication_checks,
        "sample_group_counts": {"GSE68183": counts68183, "GSE80178": counts80178},
        "exact_pair_count": len(pair_rows),
        "pair_metadata_concordance_pass": all_pair_pass,
        "evidence_registry_complete": evidence_complete,
        "accession_rows": len(participant_rows),
        "unique_analytic_independence_units": unique_units,
        "expected_counts_pass": expected_counts,
        "interpretation_boundary": decision["participant_boundary"],
    }
    (output_dir / "M01_METADATA_QC.json").write_text(json.dumps(qc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return qc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "adjudicate"), required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--gse68183-matrix")
    parser.add_argument("--gse80178-matrix")
    parser.add_argument("--pilot-matches")
    parser.add_argument("--primary-source-manifest")
    parser.add_argument("--evidence-registry")
    parser.add_argument("--output-dir")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "smoke":
        print(json.dumps({"schema_version": SCHEMA_VERSION, "mode": "SMOKE", "verdict": "PASS", "note": "No scientific outputs created."}, indent=2))
        return 0
    required = ("gse68183_matrix", "gse80178_matrix", "pilot_matches", "primary_source_manifest", "evidence_registry", "output_dir")
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        raise SystemExit(f"Missing adjudication arguments: {', '.join(missing)}")
    qc = adjudicate(args)
    print(json.dumps(qc, indent=2, ensure_ascii=False))
    return 0 if qc["verdict"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
