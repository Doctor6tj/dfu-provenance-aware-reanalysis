#!/usr/bin/env python3
"""Stream the 14 locked M07 core libraries to per-library sparse files."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
import time
from pathlib import Path


def load_converter(project_root: Path):
    path = project_root / "04_code/Python/m07_convert_csv_counts_to_sparse_mtx_v1.py"
    spec = importlib.util.spec_from_file_location("m07_pilot_converter_v1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load converter dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    manifest_path = args.library_manifest.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing overwrite: {output}")
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    if len(manifest) != 14:
        raise ValueError(f"Full core manifest must contain 14 libraries, observed {len(manifest)}")
    if len({row["participant_alias"] for row in manifest}) != 11:
        raise ValueError("Full core manifest must contain 11 participants")
    if sum(int(row["expected_cells_pre_qc"]) for row in manifest) != 45514:
        raise ValueError("Full core manifest cell total is not 45,514")
    if any(row["analysis_role"] != "CORE_FOOT_SUPPORTING_EXPLORATORY" for row in manifest):
        raise ValueError("Unexpected analysis role in full core manifest")
    if any(row["tissue_compartment"] != "FOOT_SKIN" for row in manifest):
        raise ValueError("Non-foot library in core manifest")

    converter = load_converter(root)
    output.mkdir(parents=True)
    started = time.perf_counter()
    summaries = []
    peak_observed = converter.rss_gib() or 0.0
    for row in sorted(manifest, key=lambda item: int(item["analysis_order"])):
        source = root / row["source_relative_path"]
        if not source.is_file() or source.stat().st_size != int(row["expected_compressed_bytes"]):
            raise FileNotFoundError(f"Source existence/size mismatch: {source}")
        summary = converter.convert_library(
            source=source,
            target=output / "libraries" / row["gsm_accession"],
            expected_cells=int(row["expected_cells_pre_qc"]),
            expected_features=int(row["expected_detected_feature_rows"]),
            chunk_rows=args.chunk_rows,
        )
        summary.update(
            {
                "gsm_accession": row["gsm_accession"],
                "participant_alias": row["participant_alias"],
                "biological_group": row["biological_group"],
                "source_relative_path": row["source_relative_path"],
                "expected_sha256": row["expected_sha256"],
                "source_hash_policy": row["hash_status"],
            }
        )
        summaries.append(summary)
        peak_observed = max(peak_observed, converter.rss_gib() or 0.0)
        if peak_observed > args.memory_stop_gib:
            raise MemoryError(f"Observed converter RSS {peak_observed:.3f} GiB exceeds {args.memory_stop_gib} GiB")

    overall = {
        "schema_version": "1.0",
        "module_id": "M07_SINGLE_CELL_CONTEXT",
        "created_at": converter.utc_now(),
        "status": "PASS_FULL_CORE_SPARSE_CONVERSION",
        "mode": "FULL_CORE_FOOT_SUPPORTING_ANALYSIS",
        "library_count": len(summaries),
        "participant_count": len({item["participant_alias"] for item in summaries}),
        "cells": sum(item["cells"] for item in summaries),
        "source_feature_rows": sum(item["source_feature_rows"] for item in summaries),
        "unique_features_sum_across_libraries": sum(item["unique_features"] for item in summaries),
        "nonzero_counts_sum": sum(item["nonzero_counts"] for item in summaries),
        "source_hashes_recomputed": False,
        "source_hash_authority": "Inherited COPY008 hash-matched manifest",
        "expression_normalization_performed": False,
        "condition_inference_performed": False,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "peak_observed_rss_gib": round(peak_observed, 3),
        "memory_stop_gib": args.memory_stop_gib,
        "libraries": summaries,
    }
    converter.write_json_new(output / "M07_FULL_SPARSE_CONVERSION_SUMMARY_v1.json", overall)
    print(json.dumps({key: overall[key] for key in ("status", "library_count", "participant_count", "cells", "runtime_seconds", "peak_observed_rss_gib")}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--library-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--chunk-rows", type=int, default=256)
    parser.add_argument("--memory-stop-gib", type=float, default=24.0)
    args = parser.parse_args()
    if args.chunk_rows < 1 or not math.isfinite(args.memory_stop_gib) or args.memory_stop_gib <= 0:
        raise ValueError("Invalid chunk rows or memory stop")
    try:
        return run(args)
    except Exception as exc:
        output = args.output_dir.resolve()
        if output.is_dir():
            converter = load_converter(args.project_root.resolve())
            failure = output / "M07_FULL_SPARSE_CONVERSION_FAILURE_v1.json"
            if not failure.exists():
                converter.write_json_new(
                    failure,
                    {
                        "schema_version": "1.0",
                        "module_id": "M07_SINGLE_CELL_CONTEXT",
                        "failed_at": converter.utc_now(),
                        "status": "FAILED_PRESERVED_NO_OVERWRITE",
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                        "partial_output_preserved": True,
                        "condition_inference_performed": False,
                    },
                )
        print(json.dumps({"status": "FAILED_PRESERVED_NO_OVERWRITE", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
