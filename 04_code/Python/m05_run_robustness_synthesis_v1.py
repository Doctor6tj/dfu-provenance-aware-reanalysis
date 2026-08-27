#!/usr/bin/env python3
"""M05 deterministic, null-safe robustness adjudication.

This program consumes only accepted M03/M04 outputs.  It does not recompute
expression, differential expression, meta-analysis, or pathway enrichment.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MODULE_ID = "M05_ROBUSTNESS_SYNTHESIS"
VALID_NULL = "INSUFFICIENT_INDEPENDENT_COMPATIBLE_EVIDENCE_NO_ROBUST_SIGNAL"
GENE_ROWS_EXPECTED = 18865


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, obj: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_tsv_gz(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    # filename="" and mtime=0 make the gzip object byte deterministic.
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(
                    text, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)


def read_tsv_gz(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def as_bool(value: str) -> bool:
    return value.strip().upper() == "TRUE"


def bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def same_nonzero_direction(values: Iterable[float]) -> bool:
    signs = {(value > 0) - (value < 0) for value in values}
    return len(signs) == 1 and 0 not in signs


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parameters", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    started_at = utc_now()
    start_clock = time.perf_counter()
    params_path = args.parameters.resolve()
    output_dir = args.output_directory.resolve()
    require(params_path.is_file(), f"Parameter file not found: {params_path}")
    require(not output_dir.exists(), f"Refusing to overwrite existing output: {output_dir}")
    project_root = params_path.parents[2]
    require((project_root / "04_code").is_dir(), "Cannot resolve project root")
    output_dir.mkdir(parents=True, exist_ok=False)

    try:
        params = read_json(params_path)
        require(params["module_id"] == MODULE_ID, "Wrong module parameters")
        require(params["execution_control"]["foreground_only"] is True, "Foreground policy absent")
        require(params["execution_control"]["background_allowed"] is False, "Background policy mismatch")
        require(params["execution_control"]["output_overwrite_allowed"] is False, "Overwrite policy mismatch")
        require(params["software"]["standard_library_only"] is True, "Non-standard runtime not allowed")

        input_checks: list[dict[str, Any]] = []
        resolved_inputs: dict[str, Path] = {}
        for input_id, spec in params["input_authority"].items():
            path = project_root / spec["path"]
            require(path.is_file(), f"Missing input {input_id}: {path}")
            observed = sha256_file(path)
            passed = observed == spec["sha256"].lower()
            input_checks.append(
                {
                    "input_id": input_id,
                    "relative_path": spec["path"],
                    "expected_sha256": spec["sha256"].lower(),
                    "observed_sha256": observed,
                    "pass": bool_text(passed),
                }
            )
            require(passed, f"Trust-boundary hash mismatch: {input_id}")
            resolved_inputs[input_id] = path
        write_csv(
            output_dir / "M05_input_hash_verification.csv",
            ["input_id", "relative_path", "expected_sha256", "observed_sha256", "pass"],
            input_checks,
        )

        m02_lock = read_json(resolved_inputs["m02_result_lock"])
        m03_lock = read_json(resolved_inputs["m03_result_lock"])
        m04_lock = read_json(resolved_inputs["m04_result_lock"])
        require("ACCEPTED" in m03_lock["status"] and "LOCKED" in m03_lock["status"], "M03 not accepted/locked")
        require("ACCEPTED" in m04_lock["status"] and "LOCKED" in m04_lock["status"], "M04 not accepted/locked")
        require(m02_lock.get("module_id") == "M02_COHORT_HARMONIZATION", "M02 lock mismatch")
        require(m04_lock["key_results"]["provenance_aware_independent_study_count"] == 1, "Independent-study boundary changed")
        require(m04_lock["key_results"]["independent_replication_eligible"] is False, "Unexpected replication eligibility")

        contrast_ids = [
            "all12_DFU_vs_DFS",
            "all12_DFU_vs_NFS",
            "all12_DFU_vs_FS_NAIVE",
            "n11_DFU_vs_DFS",
            "n11_DFU_vs_NFS",
            "n11_DFU_vs_FS_NAIVE",
        ]
        tables = {name: read_tsv_gz(resolved_inputs[name]) for name in contrast_ids}
        for name, rows in tables.items():
            require(len(rows) == GENE_ROWS_EXPECTED, f"Unexpected gene rows for {name}")
        reference_ids = [row["ENTREZID"] for row in tables[contrast_ids[0]]]
        require(len(reference_ids) == len(set(reference_ids)), "Duplicate ENTREZID in reference table")
        for name, rows in tables.items():
            require([row["ENTREZID"] for row in rows] == reference_ids, f"Gene order mismatch: {name}")

        all12_m04 = read_tsv_gz(resolved_inputs["m04_all12_classification"])
        n11_m04 = read_tsv_gz(resolved_inputs["m04_n11_classification"])
        require(len(all12_m04) == GENE_ROWS_EXPECTED and len(n11_m04) == GENE_ROWS_EXPECTED, "M04 classification row mismatch")
        require([row["ENTREZID"] for row in all12_m04] == reference_ids, "M04 all12 order mismatch")
        require([row["ENTREZID"] for row in n11_m04] == reference_ids, "M04 n11 order mismatch")

        result_rows: list[dict[str, Any]] = []
        tolerance = float(params["declared_tolerance"]["numeric_absolute"])
        for index, entrez in enumerate(reference_ids):
            values = {name: tables[name][index] for name in contrast_ids}
            reference = values["all12_DFU_vs_DFS"]
            for name, row in values.items():
                require(row["SYMBOL"] == reference["SYMBOL"], f"SYMBOL mismatch at {entrez}: {name}")
                require(row["GENENAME"] == reference["GENENAME"], f"GENENAME mismatch at {entrez}: {name}")

            a_dfs = float(values["all12_DFU_vs_DFS"]["logFC"])
            a_nfs = float(values["all12_DFU_vs_NFS"]["logFC"])
            a_naive = float(values["all12_DFU_vs_FS_NAIVE"]["logFC"])
            s_dfs = float(values["n11_DFU_vs_DFS"]["logFC"])
            s_nfs = float(values["n11_DFU_vs_NFS"]["logFC"])
            s_naive = float(values["n11_DFU_vs_FS_NAIVE"]["logFC"])
            q_a_dfs = float(values["all12_DFU_vs_DFS"]["adj.P.Val"])
            q_a_nfs = float(values["all12_DFU_vs_NFS"]["adj.P.Val"])
            q_a_naive = float(values["all12_DFU_vs_FS_NAIVE"]["adj.P.Val"])
            q_s_dfs = float(values["n11_DFU_vs_DFS"]["adj.P.Val"])
            q_s_nfs = float(values["n11_DFU_vs_NFS"]["adj.P.Val"])
            q_s_naive = float(values["n11_DFU_vs_FS_NAIVE"]["adj.P.Val"])

            # Cross-check the accepted M04 projection without recomputing it.
            m04a = all12_m04[index]
            m04s = n11_m04[index]
            checks = [
                abs(float(m04a["DFU_vs_DFS_logFC"]) - a_dfs),
                abs(float(m04a["DFU_vs_NFS_logFC"]) - a_nfs),
                abs(float(m04a["naive_logFC"]) - a_naive),
                abs(float(m04s["DFU_vs_DFS_logFC"]) - s_dfs),
                abs(float(m04s["DFU_vs_NFS_logFC"]) - s_nfs),
                abs(float(m04s["naive_logFC"]) - s_naive),
            ]
            require(max(checks) <= tolerance, f"M03/M04 effect mismatch at {entrez}")

            a_dfs_sig = q_a_dfs < 0.05
            a_nfs_sig = q_a_nfs < 0.05
            a_naive_sig = q_a_naive < 0.05
            s_dfs_sig = q_s_dfs < 0.05
            s_nfs_sig = q_s_nfs < 0.05
            s_naive_sig = q_s_naive < 0.05
            primary_both = a_dfs_sig and a_nfs_sig
            primary_any = a_dfs_sig or a_nfs_sig
            sensitivity_both = s_dfs_sig and s_nfs_sig
            sensitivity_any = s_dfs_sig or s_nfs_sig
            primary_same = same_nonzero_direction([a_dfs, a_nfs])
            sensitivity_same = same_nonzero_direction([s_dfs, s_nfs])
            four_way_same = same_nonzero_direction([a_dfs, a_nfs, s_dfs, s_nfs])
            dfs_profile_stable = same_nonzero_direction([a_dfs, s_dfs])
            nfs_profile_stable = same_nonzero_direction([a_nfs, s_nfs])
            naive_firewall = not (a_naive_sig and not primary_both)
            cross_study_gate = False
            primary_authority_gate = True
            robust = all(
                [
                    cross_study_gate,
                    primary_both,
                    primary_same,
                    four_way_same,
                    naive_firewall,
                    primary_authority_gate,
                ]
            )

            if robust:
                tier = "ROBUST_CROSS_STUDY_COMPATIBLE"
            elif primary_both:
                tier = "PRIMARY_BOTH_SEPARATE_INTERNAL_ONLY"
            elif primary_any:
                tier = "PRIMARY_SINGLE_SEPARATE_INTERNAL_ONLY"
            elif a_naive_sig:
                tier = "PRIMARY_NAIVE_MERGED_ONLY_NOT_ROBUST"
            elif sensitivity_any:
                tier = "SENSITIVITY_ONLY_SEPARATE_NOT_ROBUST"
            elif s_naive_sig:
                tier = "SENSITIVITY_ONLY_NAIVE_MERGED_NOT_ROBUST"
            else:
                tier = "NO_THRESHOLD_SIGNAL"

            failed: list[str] = []
            if not cross_study_gate:
                failed.append("INDEPENDENT_STUDY_COUNT_LT_2")
            if not primary_both:
                failed.append("ALL12_BOTH_SEPARATE_FDR_GATE_FAIL")
            if not primary_same:
                failed.append("ALL12_DIRECTION_GATE_FAIL")
            if not four_way_same:
                failed.append("ALL12_N11_FOUR_WAY_DIRECTION_GATE_FAIL")
            if not naive_firewall:
                failed.append("NAIVE_MERGED_CONTROL_DEPENDENCE")

            result_rows.append(
                {
                    "ENTREZID": entrez,
                    "SYMBOL": reference["SYMBOL"],
                    "GENENAME": reference["GENENAME"],
                    "all12_DFU_vs_DFS_logFC": values["all12_DFU_vs_DFS"]["logFC"],
                    "all12_DFU_vs_DFS_BH_q": values["all12_DFU_vs_DFS"]["adj.P.Val"],
                    "all12_DFU_vs_NFS_logFC": values["all12_DFU_vs_NFS"]["logFC"],
                    "all12_DFU_vs_NFS_BH_q": values["all12_DFU_vs_NFS"]["adj.P.Val"],
                    "all12_naive_logFC": values["all12_DFU_vs_FS_NAIVE"]["logFC"],
                    "all12_naive_BH_q": values["all12_DFU_vs_FS_NAIVE"]["adj.P.Val"],
                    "n11_DFU_vs_DFS_logFC": values["n11_DFU_vs_DFS"]["logFC"],
                    "n11_DFU_vs_DFS_BH_q": values["n11_DFU_vs_DFS"]["adj.P.Val"],
                    "n11_DFU_vs_NFS_logFC": values["n11_DFU_vs_NFS"]["logFC"],
                    "n11_DFU_vs_NFS_BH_q": values["n11_DFU_vs_NFS"]["adj.P.Val"],
                    "n11_naive_logFC": values["n11_DFU_vs_FS_NAIVE"]["logFC"],
                    "n11_naive_BH_q": values["n11_DFU_vs_FS_NAIVE"]["adj.P.Val"],
                    "all12_DFU_vs_DFS_BH_FDR_lt_0_05": bool_text(a_dfs_sig),
                    "all12_DFU_vs_NFS_BH_FDR_lt_0_05": bool_text(a_nfs_sig),
                    "all12_naive_BH_FDR_lt_0_05": bool_text(a_naive_sig),
                    "n11_DFU_vs_DFS_BH_FDR_lt_0_05": bool_text(s_dfs_sig),
                    "n11_DFU_vs_NFS_BH_FDR_lt_0_05": bool_text(s_nfs_sig),
                    "n11_naive_BH_FDR_lt_0_05": bool_text(s_naive_sig),
                    "primary_both_separate_gate": bool_text(primary_both),
                    "primary_same_direction_gate": bool_text(primary_same),
                    "sensitivity_both_separate": bool_text(sensitivity_both),
                    "sensitivity_same_direction": bool_text(sensitivity_same),
                    "DFS_profile_direction_stable": bool_text(dfs_profile_stable),
                    "NFS_profile_direction_stable": bool_text(nfs_profile_stable),
                    "four_way_direction_gate": bool_text(four_way_same),
                    "naive_firewall_gate": bool_text(naive_firewall),
                    "independent_study_gate": bool_text(cross_study_gate),
                    "primary_authority_gate": bool_text(primary_authority_gate),
                    "robust_cross_study_gene": bool_text(robust),
                    "evidence_tier": tier,
                    "robust_ineligibility_reasons": ";".join(failed),
                }
            )

        gene_fields = list(result_rows[0].keys())
        write_tsv_gz(
            output_dir / "M05_gene_robustness_adjudication.tsv.gz", gene_fields, result_rows
        )

        tier_counts = Counter(row["evidence_tier"] for row in result_rows)
        tier_rules: list[dict[str, str]] = []
        with resolved_inputs["tier_rules"].open("r", encoding="utf-8", newline="") as handle:
            tier_rules = list(csv.DictReader(handle))
        tier_summary = []
        for rule in tier_rules:
            tier_summary.append(
                {
                    "priority": rule["priority"],
                    "tier_id": rule["tier_id"],
                    "rule": rule["rule"],
                    "n_genes": tier_counts.get(rule["tier_id"], 0),
                    "robust_claim_eligible": rule["robust_claim_eligible"],
                    "manuscript_role": rule["manuscript_role"],
                }
            )
        write_csv(
            output_dir / "M05_evidence_tier_summary.csv",
            ["priority", "tier_id", "rule", "n_genes", "robust_claim_eligible", "manuscript_role"],
            tier_summary,
        )

        def count_true(field: str) -> int:
            return sum(row[field] == "TRUE" for row in result_rows)

        gate_rows = [
            {"gate_order": 1, "gate_id": "INDEPENDENT_COMPATIBLE_STUDIES", "observed": 1, "required": ">=2", "n_genes_passing": 0, "gate_pass": "FALSE", "hard_gate": "TRUE"},
            {"gate_order": 2, "gate_id": "ALL12_BOTH_SEPARATE_BH_FDR", "observed": count_true("primary_both_separate_gate"), "required": "both q<0.05", "n_genes_passing": count_true("primary_both_separate_gate"), "gate_pass": bool_text(count_true("primary_both_separate_gate") > 0), "hard_gate": "TRUE"},
            {"gate_order": 3, "gate_id": "ALL12_SAME_NONZERO_DIRECTION", "observed": count_true("primary_same_direction_gate"), "required": "same sign", "n_genes_passing": count_true("primary_same_direction_gate"), "gate_pass": "DESCRIPTIVE", "hard_gate": "TRUE"},
            {"gate_order": 4, "gate_id": "ALL12_N11_FOUR_WAY_DIRECTION", "observed": count_true("four_way_direction_gate"), "required": "same sign", "n_genes_passing": count_true("four_way_direction_gate"), "gate_pass": "DESCRIPTIVE", "hard_gate": "TRUE"},
            {"gate_order": 5, "gate_id": "NAIVE_MERGED_CONTROL_FIREWALL", "observed": count_true("naive_firewall_gate"), "required": "no naive-only dependence", "n_genes_passing": count_true("naive_firewall_gate"), "gate_pass": "DESCRIPTIVE", "hard_gate": "TRUE"},
            {"gate_order": 6, "gate_id": "ALL12_PRIMARY_AUTHORITY", "observed": count_true("primary_authority_gate"), "required": "all12 remains primary", "n_genes_passing": count_true("primary_authority_gate"), "gate_pass": "TRUE", "hard_gate": "TRUE"},
            {"gate_order": 7, "gate_id": "ALL_GATES_ROBUST", "observed": count_true("robust_cross_study_gene"), "required": "all six gates", "n_genes_passing": count_true("robust_cross_study_gene"), "gate_pass": "FALSE_VALID_NULL", "hard_gate": "TRUE"},
        ]
        write_csv(
            output_dir / "M05_robustness_gate_summary.csv",
            ["gate_order", "gate_id", "observed", "required", "n_genes_passing", "gate_pass", "hard_gate"],
            gate_rows,
        )

        pathway_rows = [
            {
                "analysis_id": "CROSS_STUDY_PATHWAY_ROBUSTNESS",
                "performed": "FALSE",
                "estimable": "FALSE",
                "independent_compatible_studies": 1,
                "minimum_required": 2,
                "new_gene_set_download": "FALSE",
                "status": "PATHWAY_ROBUSTNESS_NOT_ESTIMABLE",
                "reason": params["pathway_boundary"]["reason"],
                "claim_boundary": "No pathway is tested, promoted, replicated, or declared robust in M05",
            }
        ]
        write_csv(
            output_dir / "M05_pathway_synthesis_boundary.csv",
            ["analysis_id", "performed", "estimable", "independent_compatible_studies", "minimum_required", "new_gene_set_download", "status", "reason", "claim_boundary"],
            pathway_rows,
        )

        sensitivity_rows = [
            row for row in result_rows
            if row["evidence_tier"] in {"SENSITIVITY_ONLY_SEPARATE_NOT_ROBUST", "SENSITIVITY_ONLY_NAIVE_MERGED_NOT_ROBUST"}
        ]
        sensitivity_fields = [
            "ENTREZID", "SYMBOL", "GENENAME", "evidence_tier",
            "n11_DFU_vs_DFS_logFC", "n11_DFU_vs_DFS_BH_q",
            "n11_DFU_vs_NFS_logFC", "n11_DFU_vs_NFS_BH_q",
            "n11_naive_logFC", "n11_naive_BH_q", "robust_cross_study_gene",
            "robust_ineligibility_reasons",
        ]
        write_csv(
            output_dir / "M05_sensitivity_only_gene_table.csv",
            sensitivity_fields,
            [{field: row[field] for field in sensitivity_fields} for row in sensitivity_rows],
        )

        figure_rows = [
            {
                "panel": "A",
                "display_order": int(row["priority"]),
                "category": row["tier_id"],
                "n_genes": row["n_genes"],
                "status": "ROBUST" if row["tier_id"] == "ROBUST_CROSS_STUDY_COMPATIBLE" else "NOT_ROBUST",
                "figure_message": row["manuscript_role"],
            }
            for row in tier_summary
        ]
        figure_rows.extend(
            [
                {"panel": "B", "display_order": 1, "category": "Naive accession labels", "n_genes": 2, "status": "PSEUDO_REPLICATION_RISK", "figure_message": "Two accession labels do not represent two independent studies"},
                {"panel": "B", "display_order": 2, "category": "Independent compatible studies", "n_genes": 1, "status": "BELOW_MINIMUM", "figure_message": "At least two independent compatible studies were required"},
                {"panel": "B", "display_order": 3, "category": "Robust cross-study genes", "n_genes": 0, "status": "VALID_NULL", "figure_message": VALID_NULL},
            ]
        )
        write_csv(
            output_dir / "M05_figure4_source.csv",
            ["panel", "display_order", "category", "n_genes", "status", "figure_message"],
            figure_rows,
        )

        qc_rows = [
            {"qc_domain": "ENGINEERING", "status": "PASS", "finding": "All declared trust-boundary hashes matched; deterministic standard-library execution; no overwrite", "boundary": "No source or accepted upstream object was modified"},
            {"qc_domain": "STATISTICAL", "status": "PASS_VALID_NULL", "finding": "One independent compatible study is below the prespecified minimum of two", "boundary": "Meta-analysis and leave-one-study-out are not estimable"},
            {"qc_domain": "SCIENTIFIC", "status": "PASS_WITH_LIMITATION", "finding": "No gene satisfies the cross-study robustness definition", "boundary": "Sensitivity-only genes and merged-control findings are not robust biomarkers"},
            {"qc_domain": "PATHWAY", "status": "NOT_ESTIMABLE", "finding": "No prospectively locked cross-study pathway synthesis can be supported", "boundary": "No pathway discovery or promotion was performed"},
        ]
        write_csv(
            output_dir / "M05_engineering_statistical_scientific_qc.csv",
            ["qc_domain", "status", "finding", "boundary"],
            qc_rows,
        )

        all12_counts = {
            "DFU_vs_DFS": count_true("all12_DFU_vs_DFS_BH_FDR_lt_0_05"),
            "DFU_vs_NFS": count_true("all12_DFU_vs_NFS_BH_FDR_lt_0_05"),
            "DFU_vs_FS_NAIVE": count_true("all12_naive_BH_FDR_lt_0_05"),
        }
        n11_counts = {
            "DFU_vs_DFS": count_true("n11_DFU_vs_DFS_BH_FDR_lt_0_05"),
            "DFU_vs_NFS": count_true("n11_DFU_vs_NFS_BH_FDR_lt_0_05"),
            "DFU_vs_FS_NAIVE": count_true("n11_naive_BH_FDR_lt_0_05"),
        }
        require(all12_counts == {"DFU_vs_DFS": 0, "DFU_vs_NFS": 0, "DFU_vs_FS_NAIVE": 0}, "M03 primary threshold counts changed")
        require(n11_counts == {"DFU_vs_DFS": 0, "DFU_vs_NFS": 1, "DFU_vs_FS_NAIVE": 9}, "M03 sensitivity threshold counts changed")
        require(count_true("robust_cross_study_gene") == 0, "Independence gate failed to enforce valid null")

        result_summary = {
            "schema_version": "1.0",
            "module_id": MODULE_ID,
            "run_id": output_dir.name,
            "output_directory": str(output_dir),
            "status": "READY_FOR_INDEPENDENT_VALIDATION",
            "result_status": VALID_NULL,
            "started_at": started_at,
            "completed_at": utc_now(),
            "gene_rows": len(result_rows),
            "independence": {
                "naive_accession_count": 2,
                "independent_compatible_study_count": 1,
                "minimum_for_cross_study_robustness": 2,
                "independence_gate_pass": False,
                "meta_analysis_performed": False,
                "leave_one_study_out_performed": False,
            },
            "threshold_counts": {"all12_primary": all12_counts, "n11_sensitivity_only": n11_counts},
            "evidence_tier_counts": dict(sorted(tier_counts.items())),
            "robust_cross_study_gene_count": 0,
            "robust_cross_study_gene_ids": [],
            "pathway_synthesis": {
                "performed": False,
                "status": "PATHWAY_ROBUSTNESS_NOT_ESTIMABLE",
                "promoted_pathways": [],
            },
            "interpretation": [
                "No gene satisfies the prespecified cross-study robustness definition.",
                "This is a valid null/insufficient-evidence result because only one independent compatible core study is available.",
                "The n11 threshold signals are retained only as QC-sensitivity observations and are not promoted.",
            ],
            "claims_allowed": [
                "The core local-DFU evidence base contains one independent compatible study after provenance correction.",
                "No robust cross-study gene or pathway signal was established under the prespecified rules.",
            ],
            "cannot_conclude": [
                "No gene can be claimed as an independently replicated DFU biomarker.",
                "GSE68183 cannot be used as external replication of GSE80178.",
                "Sensitivity-only or merged-control findings cannot be promoted as primary discoveries.",
                "Absence of robust evidence is not evidence of biological absence.",
            ],
            "scope_firewalls": {
                "GSE199939": "EXCLUDED_FROM_CORE; background skin context only or separately labelled sensitivity analysis",
                "GSE165816": "DEFERRED_TO_M07_SINGLE_CELL_CONTEXT",
                "M06": "HEALING_OUTCOME_CONTEXT_NOT_PART_OF_M05",
            },
            "source_modification_performed": False,
            "package_installation_performed": False,
            "internet_access_performed": False,
            "background_execution_performed": False,
        }
        write_json(output_dir / "M05_result_summary.json", result_summary)

        environment = {
            "schema_version": "1.0",
            "module_id": MODULE_ID,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": sys.executable,
            "standard_library_only": True,
            "randomness": "NONE",
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "parameters_sha256": sha256_file(params_path),
        }
        write_json(output_dir / "M05_python_environment.json", environment)

        execution_log = {
            "schema_version": "1.0",
            "module_id": MODULE_ID,
            "run_id": output_dir.name,
            "started_at": started_at,
            "completed_at": utc_now(),
            "elapsed_seconds": round(time.perf_counter() - start_clock, 6),
            "command": [sys.executable, str(Path(__file__).resolve()), str(params_path), str(output_dir)],
            "foreground_execution": True,
            "input_hashes_verified_once": len(input_checks),
            "intermediate_rehashing_performed": False,
            "status": "COMPLETED_READY_FOR_VALIDATION",
        }
        write_json(output_dir / "M05_execution_log.json", execution_log)

        manifest_rows = []
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
            if path.is_file() and path.name != "M05_output_manifest.csv":
                manifest_rows.append(
                    {
                        "relative_path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "object_role": "M05_CANDIDATE_OUTPUT",
                    }
                )
        write_csv(
            output_dir / "M05_output_manifest.csv",
            ["relative_path", "bytes", "sha256", "object_role"],
            manifest_rows,
        )
        print(json.dumps({"status": "PASS", "output": str(output_dir), "robust_genes": 0, "gene_rows": len(result_rows)}))
        return 0
    except Exception as exc:
        failure = {
            "schema_version": "1.0",
            "module_id": MODULE_ID,
            "run_id": output_dir.name,
            "failed_at": utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "preserve_and_do_not_resume_or_overwrite": True,
        }
        write_json(output_dir / "M05_execution_failure.json", failure)
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
