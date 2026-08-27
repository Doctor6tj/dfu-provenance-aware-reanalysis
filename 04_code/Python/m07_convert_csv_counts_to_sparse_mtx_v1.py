#!/usr/bin/env python3
"""Stream GSE165816 CSV.GZ counts into per-library sparse Matrix Market files."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import io as scipy_io
from scipy import sparse

try:
    import psutil
except ImportError:  # optional telemetry only
    psutil = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rss_gib() -> float | None:
    if psutil is None:
        return None
    return psutil.Process().memory_info().rss / (1024**3)


def parse_gene_token(token: str) -> str:
    parsed = next(csv.reader([token]))
    if len(parsed) != 1:
        raise ValueError(f"Invalid feature token: {token[:100]!r}")
    gene = parsed[0].strip().lstrip("\ufeff")
    if not gene:
        raise ValueError("Blank feature identifier")
    return gene


def parse_count_row(line: str, expected_cells: int) -> tuple[str, np.ndarray, bool]:
    gene_token, separator, numeric_text = line.rstrip("\r\n").partition(",")
    if not separator:
        raise ValueError("Count row has no comma delimiter")
    gene = parse_gene_token(gene_token)
    values = np.fromstring(numeric_text, dtype=np.float64, sep=",")
    used_csv_fallback = False
    if values.size != expected_cells:
        tokens = next(csv.reader([line]))
        if len(tokens) != expected_cells + 1:
            raise ValueError(f"Row width {len(tokens)} != expected {expected_cells + 1}")
        gene = tokens[0].strip().lstrip("\ufeff")
        values = np.asarray(tokens[1:], dtype=np.float64)
        used_csv_fallback = True
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Non-finite count in feature {gene}")
    if np.any(values < 0):
        raise ValueError(f"Negative count in feature {gene}")
    rounded = np.rint(values)
    if not np.array_equal(values, rounded):
        raise ValueError(f"Non-integer count in feature {gene}")
    if rounded.size and rounded.max(initial=0) > np.iinfo(np.int32).max:
        raise OverflowError(f"Count exceeds int32 in feature {gene}")
    return gene, rounded.astype(np.int32, copy=False), used_csv_fallback


def convert_library(source: Path, target: Path, expected_cells: int, expected_features: int, chunk_rows: int) -> dict:
    if target.exists():
        raise FileExistsError(f"Refusing overwrite: {target}")
    target.mkdir(parents=True)
    started = time.perf_counter()
    with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
        header_line = handle.readline()
        if not header_line:
            raise ValueError(f"Empty source: {source}")
        barcodes = next(csv.reader([header_line]))
        barcodes = [barcode.strip() for barcode in barcodes]
        if len(barcodes) != expected_cells:
            raise ValueError(f"Header cells {len(barcodes)} != expected {expected_cells} for {source.name}")
        if any(not barcode for barcode in barcodes) or len(set(barcodes)) != len(barcodes):
            raise ValueError(f"Blank or duplicate source barcode in {source.name}")

        genes: list[str] = []
        matrix_chunks: list[sparse.csr_matrix] = []
        current_rows: list[sparse.csr_matrix] = []
        fallback_rows = 0
        for line_number, line in enumerate(handle, start=2):
            gene, values, used_fallback = parse_count_row(line, expected_cells)
            fallback_rows += int(used_fallback)
            genes.append(gene)
            nonzero = np.flatnonzero(values)
            current_rows.append(
                sparse.csr_matrix(
                    (values[nonzero], (np.zeros(nonzero.size, dtype=np.int32), nonzero)),
                    shape=(1, expected_cells),
                    dtype=np.int32,
                )
            )
            if len(current_rows) >= chunk_rows:
                matrix_chunks.append(sparse.vstack(current_rows, format="csr", dtype=np.int32))
                current_rows = []
        if current_rows:
            matrix_chunks.append(sparse.vstack(current_rows, format="csr", dtype=np.int32))
    if len(genes) != expected_features:
        raise ValueError(f"Feature rows {len(genes)} != expected {expected_features} for {source.name}")
    matrix = sparse.vstack(matrix_chunks, format="csr", dtype=np.int32)
    if matrix.shape != (expected_features, expected_cells):
        raise ValueError(f"Sparse shape {matrix.shape} is inconsistent for {source.name}")

    gene_to_index: dict[str, int] = {}
    unique_genes: list[str] = []
    old_to_new = np.empty(len(genes), dtype=np.int32)
    for old_index, gene in enumerate(genes):
        if gene not in gene_to_index:
            gene_to_index[gene] = len(unique_genes)
            unique_genes.append(gene)
        old_to_new[old_index] = gene_to_index[gene]
    duplicate_feature_rows = len(genes) - len(unique_genes)
    if duplicate_feature_rows:
        coo = matrix.tocoo(copy=False)
        matrix = sparse.csr_matrix(
            (coo.data, (old_to_new[coo.row], coo.col)),
            shape=(len(unique_genes), expected_cells),
            dtype=np.int32,
        )
        matrix.sum_duplicates()
    matrix.eliminate_zeros()

    temp_mtx = target / "matrix.mtx"
    final_mtx = target / "matrix.mtx.gz"
    scipy_io.mmwrite(temp_mtx, matrix, field="integer", symmetry="general")
    with temp_mtx.open("rb") as source_handle, gzip.open(final_mtx, "wb", compresslevel=6) as target_handle:
        shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
    temp_mtx.unlink()
    with gzip.open(target / "features.tsv.gz", "wt", encoding="utf-8", newline="\n") as handle:
        for gene in unique_genes:
            handle.write(f"{gene}\n")
    with gzip.open(target / "barcodes.tsv.gz", "wt", encoding="utf-8", newline="\n") as handle:
        for barcode in barcodes:
            handle.write(f"{barcode}\n")

    summary = {
        "source_file": source.name,
        "cells": expected_cells,
        "source_feature_rows": len(genes),
        "unique_features": len(unique_genes),
        "duplicate_feature_rows_summed": duplicate_feature_rows,
        "nonzero_counts": int(matrix.nnz),
        "sparsity_fraction": 1.0 - (matrix.nnz / (matrix.shape[0] * matrix.shape[1])),
        "csv_fallback_rows": fallback_rows,
        "integer_nonnegative": True,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "rss_gib_after_library": None if rss_gib() is None else round(rss_gib(), 3),
        "outputs": ["matrix.mtx.gz", "features.tsv.gz", "barcodes.tsv.gz"],
    }
    write_json_new(target / "conversion_summary.json", summary)
    return summary


def run(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    manifest_path = args.library_manifest.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing overwrite: {output}")
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    if not manifest:
        raise ValueError("Library manifest is empty")
    output.mkdir(parents=True)

    started = time.perf_counter()
    summaries = []
    peak_observed = rss_gib() or 0.0
    for row in manifest:
        source = root / row["source_relative_path"]
        if not source.is_file():
            raise FileNotFoundError(source)
        library_target = output / "libraries" / row["gsm_accession"]
        summary = convert_library(
            source=source,
            target=library_target,
            expected_cells=int(row["expected_cells_pre_qc"]),
            expected_features=int(row["expected_detected_feature_rows"]),
            chunk_rows=args.chunk_rows,
        )
        summary.update({
            "gsm_accession": row["gsm_accession"],
            "participant_alias": row["participant_alias"],
            "biological_group": row["biological_group"],
            "source_relative_path": row["source_relative_path"],
            "expected_sha256": row["expected_sha256"],
            "source_hash_policy": row["hash_status"],
        })
        summaries.append(summary)
        peak_observed = max(peak_observed, rss_gib() or 0.0)
        if peak_observed > args.memory_stop_gib:
            raise MemoryError(f"Observed RSS {peak_observed:.3f} GiB exceeds stop limit {args.memory_stop_gib} GiB")

    overall = {
        "schema_version": "1.0",
        "module_id": "M07_SINGLE_CELL_CONTEXT",
        "created_at": utc_now(),
        "status": "PASS_PILOT_SPARSE_CONVERSION",
        "mode": "TECHNICAL_PILOT_NO_CONDITION_INFERENCE",
        "library_count": len(summaries),
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
    write_json_new(output / "M07_SPARSE_CONVERSION_SUMMARY_v1.json", overall)
    print(json.dumps({"status": overall["status"], "libraries": overall["library_count"], "cells": overall["cells"], "runtime_seconds": overall["runtime_seconds"], "peak_rss_gib": overall["peak_observed_rss_gib"]}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--library-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--chunk-rows", type=int, default=256)
    parser.add_argument("--memory-stop-gib", type=float, default=12.0)
    args = parser.parse_args()
    if args.chunk_rows < 1:
        raise ValueError("chunk-rows must be positive")
    if not math.isfinite(args.memory_stop_gib) or args.memory_stop_gib <= 0:
        raise ValueError("memory-stop-gib must be positive and finite")
    try:
        return run(args)
    except Exception as exc:
        output = args.output_dir.resolve()
        if output.is_dir():
            failure = output / "M07_SPARSE_CONVERSION_FAILURE_v1.json"
            if not failure.exists():
                write_json_new(failure, {
                    "schema_version": "1.0",
                    "module_id": "M07_SINGLE_CELL_CONTEXT",
                    "failed_at": utc_now(),
                    "status": "FAILED_PRESERVED_NO_OVERWRITE",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "partial_output_preserved": True,
                    "condition_inference_performed": False,
                })
        print(json.dumps({"status": "FAILED_PRESERVED_NO_OVERWRITE", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
