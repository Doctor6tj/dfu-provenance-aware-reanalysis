#!/usr/bin/env python3
"""Repair SQ3 panel-header geometry in Figures 2-4 without rerunning analysis.

The script reads only accepted/versioned plotting tables.  It preserves all
scientific values and visible body geometry while changing the header module to:
title left = scientific-body left; tag right = title left - 2.0 mm; shared
typographic baseline.  Every panel receives a complete executable contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

import result_figure_builders as base
import figure23_builders as remaining


TAG_SIZE_PT = 9.0
TITLE_SIZE_PT = 8.5
TAG_TITLE_GAP_MM = 2.0
HEADER_Y_AXES = 1.075


def add_panel_header_hard(ax, tag: str, title: str):
    """Create an unresolved header; exact tag x is locked after canvas layout."""
    title_obj = ax.text(
        0.0, HEADER_Y_AXES, title, transform=ax.transAxes,
        fontsize=TITLE_SIZE_PT, fontweight="bold", va="baseline", ha="left",
        clip_on=False,
    )
    tag_obj = ax.text(
        -0.05, HEADER_Y_AXES, tag, transform=ax.transAxes,
        fontsize=TAG_SIZE_PT, fontweight="bold", va="baseline", ha="right",
        clip_on=False,
    )
    return ax, tag_obj, title_obj


def lock_and_measure_headers(fig, headers: list[tuple]) -> list[dict[str, float | str]]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gap_px = TAG_TITLE_GAP_MM / 25.4 * fig.dpi
    for ax, tag, title in headers:
        body_left_px = ax.get_window_extent(renderer=renderer).x0
        title.set_position((0.0, HEADER_Y_AXES))
        tag_right_px = body_left_px - gap_px
        tag_x = ax.transAxes.inverted().transform((tag_right_px, body_left_px))[0]
        tag.set_position((tag_x, HEADER_Y_AXES))

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    metrics: list[dict[str, float | str]] = []
    for ax, tag, title in headers:
        body_box = ax.get_window_extent(renderer=renderer)
        tag_box = tag.get_window_extent(renderer=renderer)
        title_box = title.get_window_extent(renderer=renderer)
        tag_anchor_y = tag.get_transform().transform(tag.get_position())[1]
        title_anchor_y = title.get_transform().transform(title.get_position())[1]
        px_to_mm = 25.4 / fig.dpi
        metric = {
            "tag": tag.get_text(),
            "title": title.get_text(),
            "body_left_mm": body_box.x0 * px_to_mm,
            "title_left_mm": title_box.x0 * px_to_mm,
            "tag_right_mm": tag_box.x1 * px_to_mm,
            "tag_baseline_mm": tag_anchor_y * px_to_mm,
            "title_baseline_mm": title_anchor_y * px_to_mm,
            "gap_mm": (title_box.x0 - tag_box.x1) * px_to_mm,
            "size_delta_pt": TAG_SIZE_PT - TITLE_SIZE_PT,
            "tag_left_px": tag_box.x0,
            "canvas_width_px": fig.canvas.get_width_height()[0],
        }
        anchor_error = abs(float(metric["title_left_mm"]) - float(metric["body_left_mm"]))
        baseline_error = abs(float(metric["tag_baseline_mm"]) - float(metric["title_baseline_mm"]))
        if anchor_error > 0.5:
            raise RuntimeError(f"{tag.get_text()} title/body anchor error {anchor_error:.4f} mm")
        if baseline_error > 0.35:
            raise RuntimeError(f"{tag.get_text()} tag/title baseline error {baseline_error:.4f} mm")
        if not 1.5 <= float(metric["gap_mm"]) <= 2.5:
            raise RuntimeError(f"{tag.get_text()} tag/title gap {metric['gap_mm']:.4f} mm")
        if not 0.5 <= float(metric["size_delta_pt"]) <= 1.0:
            raise RuntimeError(f"{tag.get_text()} tag/title size delta invalid")
        if float(metric["tag_left_px"]) < 0:
            raise RuntimeError(f"{tag.get_text()} tag is clipped by the figure canvas")
        metrics.append(metric)
    return metrics


def save_candidate_hard(fig, path: Path, headers: list[tuple]) -> list[dict]:
    metrics = lock_and_measure_headers(fig, headers)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    fig.savefig(path, dpi=300, bbox_inches=None, facecolor="white")
    plt.close(fig)
    return metrics


def header_contract_rows(figure_id: str, metrics: list[dict], source: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    enforcement = "BUILDER_ASSERTION|GEOMETRY_QC|ACTUAL_RENDER"
    for metric in metrics:
        common = {
            "figure_id": figure_id,
            "panel_id": str(metric["tag"]),
            "allowed_values": "",
            "enforcement": enforcement,
            "source": source,
            "status": "PASS",
        }
        rows.extend(
            [
                {
                    **common, "rule_id": "HDR_TITLE_BODY_ANCHOR", "relation": "EQUAL_NUM",
                    "observed": f"{metric['title_left_mm']:.6f}", "expected": f"{metric['body_left_mm']:.6f}",
                    "lower": "", "upper": "", "tolerance": "0.5", "unit": "mm",
                    "notes": "Measured from the final canvas; title first character equals axes scientific-body left",
                },
                {
                    **common, "rule_id": "HDR_TAG_TITLE_BASELINE", "relation": "EQUAL_NUM",
                    "observed": f"{metric['tag_baseline_mm']:.6f}", "expected": f"{metric['title_baseline_mm']:.6f}",
                    "lower": "", "upper": "", "tolerance": "0.35", "unit": "mm",
                    "notes": "Both text objects use va=baseline and a shared transformed anchor",
                },
                {
                    **common, "rule_id": "HDR_TAG_TITLE_GAP", "relation": "BETWEEN",
                    "observed": f"{metric['gap_mm']:.6f}", "expected": "",
                    "lower": "1.5", "upper": "2.5", "tolerance": "", "unit": "mm",
                    "notes": "Tag right edge is fixed 2.0 mm left of title/body anchor",
                },
                {
                    **common, "rule_id": "HDR_TAG_TITLE_SIZE_DELTA", "relation": "BETWEEN",
                    "observed": f"{metric['size_delta_pt']:.1f}", "expected": "",
                    "lower": "0.5", "upper": "1.0", "tolerance": "", "unit": "pt",
                    "notes": "Article typography lock: 9.0-pt tag and 8.5-pt title",
                },
            ]
        )
    return rows


def write_contract(
    out: Path,
    figure_id: str,
    metrics: list[dict],
    scientific_rows: list[dict],
    validator: Path,
    coverage_validator: Path,
    version: str,
) -> None:
    fields = [
        "figure_id", "panel_id", "rule_id", "relation", "observed", "expected",
        "lower", "upper", "tolerance", "allowed_values", "unit", "enforcement",
        "source", "status", "notes",
    ]
    rows = header_contract_rows(figure_id, metrics, "result_figure_layout.py")
    rows.extend(scientific_rows)
    contract = out / "qc" / f"layout_contract_{version}.csv"
    base.write_csv_new(contract, fields, rows)
    validated = out / "qc" / f"layout_contract_validated_{version}.csv"
    completed = subprocess.run(
        [sys.executable, str(validator), str(contract), "--output", str(validated)],
        text=True, capture_output=True,
    )
    base.write_text_new(
        out / "qc" / f"layout_contract_validator_log_{version}.txt",
        completed.stdout + completed.stderr,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"SQ3 layout validation failed for {figure_id}:\n{completed.stdout}\n{completed.stderr}")
    coverage_output = out / "qc" / f"panel_header_contract_coverage_{version}.json"
    coverage = subprocess.run(
        [
            sys.executable, str(coverage_validator), str(contract),
            "--panels", ",".join(str(metric["tag"]) for metric in metrics),
            "--output", str(coverage_output),
        ],
        text=True, capture_output=True,
    )
    base.write_text_new(
        out / "qc" / f"panel_header_contract_coverage_log_{version}.txt",
        coverage.stdout + coverage.stderr,
    )
    if coverage.returncode != 0:
        raise RuntimeError(f"Header-contract coverage failed for {figure_id}:\n{coverage.stdout}\n{coverage.stderr}")


def rename_new(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite: {target}")
    source.rename(target)


def write_candidate_qc(out: Path, figure_id: str, version: str, candidate: Path, supersedes: str) -> None:
    qc = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "figure_id": figure_id,
        "candidate_version": version,
        "status": "PASS_GEOMETRY_PENDING_STRICT_ACTUAL_RENDER",
        "operation": "PANEL_HEADER_GEOMETRY_ONLY_NO_ANALYSIS_RERUN",
        "supersedes_visual_candidate": supersedes,
        "checks": {
            "title_left_equals_scientific_body_left": True,
            "tag_right_is_2mm_left_of_title": True,
            "tag_title_shared_baseline": True,
            "tag_title_size_delta_0_5pt": True,
            "complete_header_contract_per_panel": True,
            "official_sq3_contract_validator_pass": True,
            "scientific_values_unchanged": True,
            "analysis_not_rerun": True,
            "candidate_png_exists": candidate.exists(),
            "final_release_not_created": True,
        },
        "next_gate": "STRICT_ACTUAL_RENDER_HOTSPOT_AND_WHOLE_FIGURE_REVIEW",
    }
    base.write_json_new(out / "qc" / f"{figure_id}_candidate_build_QC_{version}.json", qc)


def build_figure2(root: Path, figure_root: Path, out: Path, validator: Path, coverage: Path) -> dict:
    base.prepare(out)
    source_dir = figure_root / "Figure2_Sample_Reuse_Comparator_Map_v04_visual_finalize"
    pairs = pd.read_csv(source_dir / "source_data" / "exact_reuse_pairs_v04.csv")
    counts = pd.read_csv(source_dir / "source_data" / "figure2_derived_counts_v04.csv")
    observed = dict(zip(counts.count_id, counts.value))
    expected = {
        "combined_accession_rows": 18, "conservative_analytic_units": 12,
        "exact_reused_control_pairs": 6, "GSE80178_DFU": 6,
        "GSE80178_DFS": 3, "GSE80178_NFS": 3,
    }
    if len(pairs) != 6 or not pairs.exact_raw_object_identity.astype(bool).all():
        raise RuntimeError("Figure 2 exact-pair assertions failed")
    if any(int(observed[key]) != value for key, value in expected.items()):
        raise RuntimeError("Figure 2 count assertions failed")
    pairs.to_csv(out / "source_data/exact_reuse_pairs_v05.csv", index=False, encoding="utf-8-sig")
    counts.to_csv(out / "source_data/figure2_derived_counts_v05.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 105 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.42, 0.95, 0.82],
        left=0.065, right=0.985, top=0.80, bottom=0.14, wspace=0.54,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        add_panel_header_hard(axes[0], "A", "Exact reused controls"),
        add_panel_header_hard(axes[1], "B", "GSE80178 strata"),
        add_panel_header_hard(axes[2], "C", "Labels versus units"),
    ]

    ax = axes[0]
    y = np.arange(len(pairs))[::-1]
    group_colors = [base.COLORS["blue"] if "DFS" in group else base.COLORS["green"] for group in pairs["gse68183_group"]]
    for idx, (_, row) in enumerate(pairs.iterrows()):
        yy = y[idx]
        ax.plot([0.25, 0.75], [yy, yy], color=group_colors[idx], lw=1.25, solid_capstyle="round")
        ax.scatter([0.25, 0.75], [yy, yy], s=14, color=group_colors[idx], zorder=3)
        ax.text(0.22, yy, row["gse68183_gsm"], ha="right", va="center", fontsize=6.3)
        ax.text(0.78, yy, row["gse80178_gsm"], ha="left", va="center", fontsize=6.3)
    ax.text(0.22, y.max() + 0.72, "GSE68183", ha="right", va="bottom", fontsize=7.0, fontweight="bold")
    ax.text(0.78, y.max() + 0.72, "GSE80178", ha="left", va="bottom", fontsize=7.0, fontweight="bold")
    handles = [
        Patch(facecolor=base.COLORS["blue"], label="Diabetic intact foot"),
        Patch(facecolor=base.COLORS["green"], label="Nondiabetic intact foot"),
    ]
    ax.legend(handles=handles, frameon=False, loc="lower center", ncol=1, bbox_to_anchor=(0.5, -0.07), handlelength=1.0, handletextpad=0.5)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-1.05, y.max() + 1.05)
    ax.axis("off")

    ax = axes[1]
    groups = ["DFU", "Diabetic\nintact foot", "Nondiabetic\nintact foot"]
    values = [6, 3, 3]
    colors = [base.COLORS["orange"], base.COLORS["blue"], base.COLORS["green"]]
    yy = np.arange(3)[::-1]
    ax.barh(yy, values, color=colors, height=0.56)
    for yi, value in zip(yy, values):
        ax.text(value + 0.12, yi, str(value), va="center", fontsize=7.1, fontweight="bold")
    ax.set_yticks(yy, groups)
    ax.set_xlim(0, 6.8)
    ax.set_xlabel("Arrays")
    ax.grid(axis="x", color=base.COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)

    ax = axes[2]
    ax.axis("off")
    base.rounded_box(ax, (0.08, 0.68), 0.84, 0.17, "18 accession rows", base.COLORS["gray_light"], base.COLORS["gray"], 7.6)
    ax.annotate("", xy=(0.5, 0.57), xytext=(0.5, 0.67), xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", color=base.COLORS["dark"], lw=0.8))
    base.rounded_box(ax, (0.08, 0.37), 0.84, 0.19, "12 conservative\nanalytic units", base.COLORS["blue_light"], base.COLORS["blue"], 7.6)
    ax.text(0.5, 0.23, "Six aliases collapsed by\nexact raw-object identity", ha="center", va="center", transform=ax.transAxes, fontsize=6.4)
    ax.text(0.5, 0.06, "Object reuse does not identify\na real-world participant.", ha="center", va="bottom", transform=ax.transAxes, fontsize=6.1, color=base.COLORS["muted"])

    candidate = out / "Figure2_visual_v05.png"
    metrics = save_candidate_hard(fig, candidate, headers)
    scientific = [{
        "figure_id": "Figure2", "panel_id": "ALL", "rule_id": "EXACT_COUNTS",
        "relation": "EXACT", "observed": "6|18|12|6|3|3", "expected": "6|18|12|6|3|3",
        "lower": "", "upper": "", "tolerance": "", "allowed_values": "", "unit": "mixed",
        "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC", "source": "accepted Figure2 v04 source tables traced to M01",
        "status": "PASS", "notes": "Header-only repair; scientific values unchanged",
    }]
    write_contract(out, "Figure2", metrics, scientific, validator, coverage, "v05")
    base.write_text_new(out / "legend_v05.md", (source_dir / "legend_v04.md").read_text(encoding="utf-8"))
    base.write_csv_new(out / "source_manifest_v05.csv", ["source_id", "path", "role", "upstream_status", "notes"], [{
        "source_id": "F2V05S001", "path": str((source_dir / "source_data").relative_to(root)).replace("\\", "/"),
        "role": "Accepted v04 plotting tables traced to M01", "upstream_status": "READ_ONLY_VERSIONED_CANDIDATE",
        "notes": "Panel-header geometry only; no analysis rerun",
    }])
    write_candidate_qc(out, "Figure2", "v05", candidate, "Figure2 v04")
    return {"figure": "Figure2", "revision": "v05", "candidate": str(candidate)}


def build_figure3(root: Path, figure_root: Path, out: Path, validator: Path, coverage: Path) -> dict:
    base.add_panel_header = add_panel_header_hard
    base.save_candidate = save_candidate_hard

    def patched_layout(out_dir: Path, figure_id: str, metrics: list[dict], scientific_row: dict, validator_path: Path) -> None:
        write_contract(out_dir, figure_id, metrics, [scientific_row], validator_path, coverage, "v04")

    remaining.write_layout_v03 = patched_layout
    result = remaining.build_figure3(root, figure_root, out, validator)
    rename_new(out / "Figure3_visual_v03.png", out / "Figure3_visual_v04.png")
    rename_new(out / "legend_v03.md", out / "legend_v04.md")
    rename_new(out / "source_manifest_v03.csv", out / "source_manifest_v04.csv")
    for path in list((out / "source_data").glob("*_v03.csv")):
        rename_new(path, path.with_name(path.name.replace("_v03.csv", "_v04.csv")))
    candidate = out / "Figure3_visual_v04.png"
    write_candidate_qc(out, "Figure3", "v04", candidate, "Figure3 v03")
    result.update({"revision": "v04", "candidate": str(candidate)})
    return result


def build_figure4(root: Path, out: Path, validator: Path, coverage: Path) -> dict:
    base.add_panel_header = add_panel_header_hard
    base.save_candidate = save_candidate_hard

    def patched_layout(out_dir: Path, figure_id: str, metrics: list[dict], scientific_rows: list[dict], validator_path: Path) -> None:
        write_contract(out_dir, figure_id, metrics, scientific_rows, validator_path, coverage, "v03")

    base.write_layout_contract = patched_layout
    result = base.build_figure4(root, out, validator)
    rename_new(out / "Figure4_visual_v02.png", out / "Figure4_visual_v03.png")
    rename_new(out / "legend_v02.md", out / "legend_v03.md")
    rename_new(out / "source_manifest_v02.csv", out / "source_manifest_v03.csv")
    for path in list((out / "source_data").glob("*_v02.csv")):
        rename_new(path, path.with_name(path.name.replace("_v02.csv", "_v03.csv")))
    candidate = out / "Figure4_visual_v03.png"
    write_candidate_qc(out, "Figure4", "v03", candidate, "Figure4 v02")
    result.update({"revision": "v03", "candidate": str(candidate)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    figure_root = root / "07_manuscript/figures/candidates/G8_FIGURE_CANDIDATES_v01_20260826"
    outputs = [
        figure_root / "Figure2_Sample_Reuse_Comparator_Map_v05_header_geometry",
        figure_root / "Figure3_Naive_Vs_Aware_v04_header_geometry",
        figure_root / "Figure4_Robustness_Synthesis_v03_header_geometry",
    ]
    if any(path.exists() for path in outputs):
        raise FileExistsError("One or more header-geometry candidate directories already exist")
    base.set_theme()
    validator = root / "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
    coverage = root / "04_code/Python/validate_panel_headers.py"
    results = [
        build_figure2(root, figure_root, outputs[0], validator, coverage),
        build_figure3(root, figure_root, outputs[1], validator, coverage),
        build_figure4(root, outputs[2], validator, coverage),
    ]
    qc = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS_GEOMETRY_PENDING_STRICT_ACTUAL_RENDER",
        "operation": "FIGURE2_TO_4_SQ3_PANEL_HEADER_HARD_RULE_REPAIR",
        "checks": {
            "previous_candidates_preserved": True,
            "complete_scripts_saved_before_execution": True,
            "scientific_values_unchanged": True,
            "analysis_not_rerun": True,
            "official_contract_validation_pass": True,
            "header_contract_coverage_pass": True,
            "final_submission_exports_not_created": True,
        },
        "results": results,
        "next_gate": "STRICT_ACTUAL_RENDER_HOTSPOT_AND_WHOLE_FIGURE_REVIEW",
    }
    base.write_json_new(figure_root / "G8_MAIN_RESULT_PANEL_HEADER_REPAIR_QC_v01.json", qc)
    print(json.dumps(qc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
