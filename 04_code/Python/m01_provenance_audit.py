#!/usr/bin/env python3
"""Entry scaffold for M01 provenance audit.

Smoke mode validates the candidate registry without creating analysis outputs.
Full mode is deliberately blocked until an active L1 scientific-question lock
exists and every included source has a non-pending location.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any


REQUIRED_REGISTRY_COLUMNS = {
    "dataset_id",
    "source_type",
    "candidate_role",
    "organism_required",
    "tissue_role",
    "independence_unit",
    "status",
    "source_location",
    "notes",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(handle) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def load_registry(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_REGISTRY_COLUMNS - columns)
        if missing:
            raise ValueError(f"Missing registry columns: {', '.join(missing)}")
        rows = list(reader)

    dataset_ids = [row["dataset_id"].strip() for row in rows]
    duplicates = sorted({value for value in dataset_ids if dataset_ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate dataset_id values: {', '.join(duplicates)}")
    if not rows:
        raise ValueError("Candidate dataset registry is empty")
    return rows, sorted(columns)


def active_lock_ids(lock_registry: Path) -> set[str]:
    if not lock_registry.exists():
        return set()
    with lock_registry.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row.get("lock_id", "").strip()
            for row in csv.DictReader(handle)
            if row.get("status", "").strip().upper() == "ACTIVE"
        }


def smoke_report(registry: Path, rows: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    return {
        "module_id": "M01_PROVENANCE_AUDIT",
        "mode": "SMOKE",
        "verdict": "PASS",
        "registry": str(registry),
        "registry_sha256": sha256_file(registry),
        "row_count": len(rows),
        "columns": columns,
        "status_counts": {
            status: sum(row["status"].strip() == status for row in rows)
            for status in sorted({row["status"].strip() for row in rows})
        },
        "note": "Schema validation only; no dataset identity or scientific result was produced.",
    }


def execute_guard(rows: list[dict[str, str]], lock_registry: Path) -> None:
    locks = active_lock_ids(lock_registry)
    if "L1_SCIENTIFIC_QUESTION_v1" not in locks:
        raise RuntimeError("Full M01 execution blocked: active L1 scientific-question lock is absent")

    unresolved = [
        row["dataset_id"]
        for row in rows
        if row["status"].strip().upper() != "EXCLUDED"
        and row["source_location"].strip().upper().startswith("PENDING")
    ]
    if unresolved:
        raise RuntimeError(
            "Full M01 execution blocked: unresolved source locations for " + ", ".join(unresolved)
        )


def inventory_cel_archive(path: Path, dataset_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tarfile.open(path, mode="r") as archive:
        members = sorted(
            (member for member in archive.getmembers() if member.isfile() and member.name.lower().endswith(".cel.gz")),
            key=lambda member: member.name,
        )
        for member in members:
            compressed = archive.extractfile(member)
            if compressed is None:
                raise RuntimeError(f"Cannot extract tar member: {member.name}")
            with gzip.GzipFile(fileobj=compressed, mode="rb") as decompressed:
                digest, size = sha256_stream(decompressed)
            gsm_match = re.search(r"GSM\d+", Path(member.name).name, flags=re.IGNORECASE)
            records.append(
                {
                    "dataset_id": dataset_id,
                    "gsm_accession": gsm_match.group(0).upper() if gsm_match else "",
                    "archive_member": member.name,
                    "compressed_size_bytes": member.size,
                    "decompressed_size_bytes": size,
                    "decompressed_cel_sha256": digest,
                }
            )
    if not records:
        raise RuntimeError(f"No CEL.gz members found in {path}")
    return records


def exact_cross_dataset_matches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_hash.setdefault(str(record["decompressed_cel_sha256"]), []).append(record)

    matches: list[dict[str, Any]] = []
    for digest, group in sorted(by_hash.items()):
        left = sorted(
            (row for row in group if row["dataset_id"] == "GSE80178"),
            key=lambda row: row["archive_member"],
        )
        right = sorted(
            (row for row in group if row["dataset_id"] == "GSE68183"),
            key=lambda row: row["archive_member"],
        )
        for row_80178 in left:
            for row_68183 in right:
                matches.append(
                    {
                        "decompressed_cel_sha256": digest,
                        "gse80178_gsm": row_80178["gsm_accession"],
                        "gse80178_member": row_80178["archive_member"],
                        "gse68183_gsm": row_68183["gsm_accession"],
                        "gse68183_member": row_68183["archive_member"],
                        "decompressed_size_bytes": row_80178["decompressed_size_bytes"],
                        "identity_evidence": "EXACT_DECOMPRESSED_CEL_SHA256",
                    }
                )
    return matches


def verify_manifest_hash(path: Path, manifest: Path) -> str:
    expected: list[str] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if Path(row.get("path_or_accession", "")).name == path.name:
                expected.append(row.get("sha256", "").strip().lower())
    expected = [value for value in expected if value]
    if len(expected) != 1:
        raise RuntimeError(f"Expected exactly one manifest row for {path.name}; found {len(expected)}")
    observed = sha256_file(path)
    if observed != expected[0]:
        raise RuntimeError(f"Source manifest hash mismatch: {path}")
    return observed


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_overlap_pilot(
    gse80178_tar: Path,
    gse68183_tar: Path,
    source_manifest: Path,
    output_dir: Path,
) -> dict[str, Any]:
    input_hashes = {
        "GSE80178_RAW.tar": verify_manifest_hash(gse80178_tar, source_manifest),
        "GSE68183_RAW.tar": verify_manifest_hash(gse68183_tar, source_manifest),
        "SOURCE_FILE_MANIFEST.csv": sha256_file(source_manifest),
    }
    records = inventory_cel_archive(gse80178_tar, "GSE80178") + inventory_cel_archive(
        gse68183_tar, "GSE68183"
    )
    matches = exact_cross_dataset_matches(records)
    count_80178 = sum(row["dataset_id"] == "GSE80178" for row in records)
    count_68183 = sum(row["dataset_id"] == "GSE68183" for row in records)
    unique_hashes_80178 = len(
        {row["decompressed_cel_sha256"] for row in records if row["dataset_id"] == "GSE80178"}
    )
    unique_hashes_68183 = len(
        {row["decompressed_cel_sha256"] for row in records if row["dataset_id"] == "GSE68183"}
    )
    expected_structure = count_80178 == 12 and count_68183 == 6
    expected_overlap = len(matches) == 6
    verdict = "PASS" if expected_structure and expected_overlap else "HUMAN_DECISION_REQUIRED"

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "cel_identity_inventory.csv",
        records,
        [
            "dataset_id",
            "gsm_accession",
            "archive_member",
            "compressed_size_bytes",
            "decompressed_size_bytes",
            "decompressed_cel_sha256",
        ],
    )
    write_csv(
        output_dir / "cross_dataset_exact_matches.csv",
        matches,
        [
            "decompressed_cel_sha256",
            "gse80178_gsm",
            "gse80178_member",
            "gse68183_gsm",
            "gse68183_member",
            "decompressed_size_bytes",
            "identity_evidence",
        ],
    )
    summary = {
        "schema_version": "1.0",
        "module_id": "M01_PROVENANCE_AUDIT",
        "run_type": "T3_PILOT",
        "verdict": verdict,
        "input_hashes": input_hashes,
        "cel_member_counts": {"GSE80178": count_80178, "GSE68183": count_68183},
        "unique_decompressed_cel_hashes": {
            "GSE80178": unique_hashes_80178,
            "GSE68183": unique_hashes_68183,
        },
        "exact_cross_dataset_matches": len(matches),
        "expected_structure_pass": expected_structure,
        "expected_overlap_pass": expected_overlap,
        "scientific_boundary": "Exact decompressed CEL identity proves shared raw sample objects and invalidates treating all shared samples as independent validation evidence; it does not by itself resolve participant identity or comparator biology.",
        "outputs": ["cel_identity_inventory.csv", "cross_dataset_exact_matches.csv"],
    }
    (output_dir / "PILOT_QC.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="M01 DFU source-provenance audit scaffold")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--mode", choices=("smoke", "pilot", "full"), default="smoke")
    parser.add_argument(
        "--lock-registry",
        default="00_project_control/state_handoff/LOCK_REGISTRY.csv",
    )
    parser.add_argument("--output", help="JSON report path; omitted in smoke mode by default")
    parser.add_argument("--gse80178-raw-tar")
    parser.add_argument("--gse68183-raw-tar")
    parser.add_argument("--source-manifest")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    registry = Path(args.registry).expanduser().resolve()
    rows, columns = load_registry(registry)
    report = smoke_report(registry, rows, columns)

    if args.mode == "pilot":
        required = {
            "--gse80178-raw-tar": args.gse80178_raw_tar,
            "--gse68183-raw-tar": args.gse68183_raw_tar,
            "--source-manifest": args.source_manifest,
            "--output-dir": args.output_dir,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError("Pilot mode missing arguments: " + ", ".join(missing))
        summary = run_overlap_pilot(
            Path(args.gse80178_raw_tar).expanduser().resolve(),
            Path(args.gse68183_raw_tar).expanduser().resolve(),
            Path(args.source_manifest).expanduser().resolve(),
            Path(args.output_dir).expanduser().resolve(),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["verdict"] == "PASS" else 2

    if args.mode == "full":
        execute_guard(rows, Path(args.lock_registry).expanduser().resolve())
        raise RuntimeError(
            "Full provenance audit implementation is not promoted until L1 approval and source-map completion"
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
