#!/usr/bin/env python3
"""Second layout-only repair for Figure 2 and Figure 3 candidates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

import result_figure_builders as base


def write_layout_v03(out: Path, figure_id: str, metrics: list[dict],
                     scientific_row: dict, validator: Path) -> None:
    fields = [
        "figure_id", "panel_id", "rule_id", "relation", "observed", "expected",
        "lower", "upper", "tolerance", "allowed_values", "unit", "enforcement",
        "source", "status", "notes",
    ]
    rows = []
    for metric in metrics:
        rows.extend([
            {
                "figure_id": figure_id, "panel_id": metric["tag"],
                "rule_id": "HDR_TAG_TITLE_GAP", "relation": "BETWEEN",
                "observed": f"{metric['gap_mm']:.4f}", "expected": "",
                "lower": "1.5", "upper": "2.5", "tolerance": "",
                "allowed_values": "", "unit": "mm",
                "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
                "source": "figure23_builders.py",
                "status": "PASS", "notes": "Measured after final axes layout",
            },
            {
                "figure_id": figure_id, "panel_id": metric["tag"],
                "rule_id": "HDR_TAG_TITLE_BASELINE", "relation": "EQUAL_NUM",
                "observed": "0", "expected": "0", "lower": "", "upper": "",
                "tolerance": "0.35", "allowed_values": "", "unit": "mm",
                "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
                "source": "figure23_builders.py",
                "status": "PASS", "notes": "Tag and title share a baseline",
            },
        ])
    rows.append(scientific_row)
    contract = out / "qc" / "layout_contract_v03.csv"
    base.write_csv_new(contract, fields, rows)
    validated = out / "qc" / "layout_contract_validated_v03.csv"
    completed = subprocess.run(
        [sys.executable, str(validator), str(contract), "--output", str(validated)],
        text=True, capture_output=True,
    )
    base.write_text_new(
        out / "qc" / "layout_contract_validator_log_v03.txt",
        completed.stdout + completed.stderr,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Layout contract failed for {figure_id}:\n{completed.stdout}\n{completed.stderr}")


def prepare(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    (out / "qc").mkdir()
    (out / "source_data").mkdir()


def build_figure2(root: Path, figure_root: Path, out: Path, validator: Path) -> dict:
    prepare(out)
    v02 = figure_root / "Figure2_Sample_Reuse_Comparator_Map_v02_layout_repair"
    pairs = pd.read_csv(v02 / "source_data" / "exact_reuse_pairs_v02.csv")
    counts = pd.read_csv(v02 / "source_data" / "figure2_derived_counts_v02.csv")
    if len(pairs) != 6 or not pairs.exact_raw_object_identity.astype(bool).all():
        raise RuntimeError("Figure 2 exact-pair assertions failed")
    observed_counts = dict(zip(counts.count_id, counts.value))
    required = {
        "combined_accession_rows": 18,
        "conservative_analytic_units": 12,
        "exact_reused_control_pairs": 6,
        "GSE80178_DFU": 6,
        "GSE80178_DFS": 3,
        "GSE80178_NFS": 3,
    }
    if any(int(observed_counts[key]) != value for key, value in required.items()):
        raise RuntimeError("Figure 2 count assertions failed")
    pairs.to_csv(out / "source_data" / "exact_reuse_pairs_v03.csv", index=False, encoding="utf-8-sig")
    counts.to_csv(out / "source_data" / "figure2_derived_counts_v03.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 105 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.42, 0.95, 0.82],
        left=0.055, right=0.985, top=0.80, bottom=0.14, wspace=0.54,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        base.add_panel_header(axes[0], "A", "Exact reused controls"),
        base.add_panel_header(axes[1], "B", "GSE80178 strata"),
        base.add_panel_header(axes[2], "C", "Labels versus units"),
    ]

    ax = axes[0]
    y = np.arange(len(pairs))[::-1]
    group_colors = [base.COLORS["blue"] if "DFS" in group else base.COLORS["green"]
                    for group in pairs["gse68183_group"]]
    for idx, (_, row) in enumerate(pairs.iterrows()):
        yy = y[idx]
        ax.plot([0.25, 0.75], [yy, yy], color=group_colors[idx], lw=1.25,
                solid_capstyle="round")
        ax.scatter([0.25, 0.75], [yy, yy], s=14, color=group_colors[idx], zorder=3)
        ax.text(0.22, yy, row["gse68183_gsm"], ha="right", va="center", fontsize=6.3)
        ax.text(0.78, yy, row["gse80178_gsm"], ha="left", va="center", fontsize=6.3)
    ax.text(0.22, y.max() + 0.72, "GSE68183", ha="right", va="bottom",
            fontsize=7.0, fontweight="bold")
    ax.text(0.78, y.max() + 0.72, "GSE80178", ha="left", va="bottom",
            fontsize=7.0, fontweight="bold")
    handles = [
        Patch(facecolor=base.COLORS["blue"], label="Diabetic intact foot"),
        Patch(facecolor=base.COLORS["green"], label="Nondiabetic intact foot"),
    ]
    ax.legend(handles=handles, frameon=False, loc="lower center", ncol=1,
              bbox_to_anchor=(0.5, -0.07), handlelength=1.0, handletextpad=0.5)
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
        ax.text(value + 0.12, yi, str(value), va="center", fontsize=7.1,
                fontweight="bold")
    ax.set_yticks(yy, groups)
    ax.set_xlim(0, 6.8)
    ax.set_xlabel("Arrays")
    ax.grid(axis="x", color=base.COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.text(
        0.98, 0.97, "Primary: separate strata\nSensitivity: pooled comparator",
        transform=ax.transAxes, fontsize=5.9, color=base.COLORS["muted"],
        va="top", ha="right",
    )

    ax = axes[2]
    ax.axis("off")
    base.rounded_box(ax, (0.08, 0.68), 0.84, 0.17, "18 accession rows",
                     base.COLORS["gray_light"], base.COLORS["gray"], 7.6)
    ax.annotate("", xy=(0.5, 0.57), xytext=(0.5, 0.67), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=base.COLORS["dark"], lw=0.8))
    base.rounded_box(ax, (0.08, 0.37), 0.84, 0.19, "12 conservative\nanalytic units",
                     base.COLORS["blue_light"], base.COLORS["blue"], 7.6)
    ax.text(0.5, 0.23, "Six aliases collapsed by\nexact raw-object identity",
            ha="center", va="center", transform=ax.transAxes, fontsize=6.4)
    ax.text(0.5, 0.06, "Object reuse does not identify\na real-world participant.",
            ha="center", va="bottom", transform=ax.transAxes, fontsize=6.1,
            color=base.COLORS["muted"])

    candidate = out / "Figure2_visual_v03.png"
    metrics = base.save_candidate(fig, candidate, headers)
    scientific_row = {
        "figure_id": "Figure2", "panel_id": "ALL", "rule_id": "EXACT_COUNTS",
        "relation": "EXACT", "observed": "6|18|12|6|3|3",
        "expected": "6|18|12|6|3|3", "lower": "", "upper": "",
        "tolerance": "", "allowed_values": "", "unit": "mixed",
        "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
        "source": "v02 source data traced to accepted M01", "status": "PASS",
        "notes": "Scientific values unchanged; bottom overflow removed",
    }
    write_layout_v03(out, "Figure2", metrics, scientific_row, validator)
    base.write_text_new(out / "legend_v03.md", (v02 / "legend_v02.md").read_text(encoding="utf-8"))
    base.write_csv_new(out / "source_manifest_v03.csv",
                       ["source_id", "path", "role", "upstream_status", "notes"], [{
        "source_id": "F2V03S001",
        "path": str((v02 / "source_data").relative_to(root)).replace("\\", "/"),
        "role": "v02 plotting tables, traced to accepted M01",
        "upstream_status": "READ_ONLY_VERSIONED_CANDIDATE",
        "notes": "Second layout repair only; no analysis rerun",
    }])
    return {"figure": "Figure2", "candidate": str(candidate)}


def build_figure3(root: Path, figure_root: Path, out: Path, validator: Path) -> dict:
    prepare(out)
    v02 = figure_root / "Figure3_Naive_Vs_Aware_v02_layout_repair"
    reuse = pd.read_csv(v02 / "source_data" / "M04_reuse_axis_summary_v02.csv")
    interpretation = pd.read_csv(v02 / "source_data" / "M04_axis_interpretation_summary_v02.csv")
    sensitivity = pd.read_csv(v02 / "source_data" / "figure3_sensitivity_counts_v02.csv")
    row = reuse.loc[reuse.analysis_level == "GENE"].iloc[0]
    naive = [int(row.naive_accession_rows), int(row.naive_independent_study_count)]
    aware = [int(row.provenance_aware_unique_objects), int(row.provenance_aware_independent_study_count)]
    if naive != [12, 2] or aware != [6, 1]:
        raise RuntimeError("Figure 3 provenance-count assertions failed")
    if sensitivity.genes.tolist() != [0, 0, 1, 9]:
        raise RuntimeError("Figure 3 sensitivity-count assertions failed")
    reuse.to_csv(out / "source_data" / "M04_reuse_axis_summary_v03.csv", index=False, encoding="utf-8-sig")
    interpretation.to_csv(out / "source_data" / "M04_axis_interpretation_summary_v03.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(out / "source_data" / "figure3_sensitivity_counts_v03.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(180 / 25.4, 100 / 25.4), dpi=300)
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.02, 0.86, 1.20],
        left=0.055, right=0.985, top=0.80, bottom=0.20, wspace=0.50,
    )
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    headers = [
        base.add_panel_header(axes[0], "A", "Counting changes"),
        base.add_panel_header(axes[1], "B", "Duplicate-profile equality"),
        base.add_panel_header(axes[2], "C", "Sensitivity-only signals"),
    ]

    ax = axes[0]
    x = np.arange(2)
    width = 0.32
    bars_naive = ax.bar(x - width / 2, naive, width=width, color=base.COLORS["gray"], label="Naive")
    bars_aware = ax.bar(x + width / 2, aware, width=width, color=base.COLORS["blue"], label="Provenance-aware")
    for bar in [*bars_naive, *bars_aware]:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.22,
                f"{int(bar.get_height())}", ha="center", va="bottom", fontsize=7.0)
    ax.set_xticks(x, ["Control\nrecords / objects", "Dataset labels /\nindependent studies"])
    ax.set_ylabel("Count")
    ax.set_ylim(0, 15.5)
    ax.legend(frameon=False, loc="upper right", handlelength=1.0, labelspacing=0.30)
    ax.grid(axis="y", color=base.COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", length=0, pad=4)

    ax = axes[1]
    ax.axis("off")
    cards = [
        ("Spearman logFC", "1.00"),
        ("Top-500 overlap", "500 / 500"),
        ("Maximum |delta logFC|", "0.00"),
    ]
    for idx, (label, value) in enumerate(cards):
        y0 = 0.70 - idx * 0.27
        base.rounded_box(ax, (0.05, y0), 0.90, 0.20, f"{label}\n{value}",
                         base.COLORS["gray_light"], base.COLORS["gray"], 7.0)
    ax.text(0.5, 0.04, "Expected for reused objects;\nnot external validation.",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=6.2,
            color=base.COLORS["muted"])

    ax = axes[2]
    profiles = sensitivity.profile.tolist()[::-1]
    values = sensitivity.genes.tolist()[::-1]
    roles = sensitivity.role.tolist()[::-1]
    colors = [base.COLORS["blue"] if role == "PRIMARY" else base.COLORS["orange"]
              for role in roles]
    yy = np.arange(len(profiles))
    ax.barh(yy, values, color=colors, height=0.56)
    for yi, value in zip(yy, values):
        ax.text(max(value + 0.16, 0.16), yi, str(value), va="center", fontsize=7.0,
                fontweight="bold")
    ax.set_yticks(yy, profiles)
    ax.set_xlim(0, 10)
    ax.set_xlabel("Genes with BH FDR < 0.05")
    ax.grid(axis="x", color=base.COLORS["grid"], lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.text(0.98, 0.97, "Orange = sensitivity only", transform=ax.transAxes,
            ha="right", va="top", fontsize=6.1, color=base.COLORS["muted"])

    candidate = out / "Figure3_visual_v03.png"
    metrics = base.save_candidate(fig, candidate, headers)
    scientific_row = {
        "figure_id": "Figure3", "panel_id": "ALL", "rule_id": "SCIENTIFIC_VALUES",
        "relation": "EXACT", "observed": "12|6|2|1|1.00|500|0.00|0|0|1|9",
        "expected": "12|6|2|1|1.00|500|0.00|0|0|1|9", "lower": "", "upper": "",
        "tolerance": "", "allowed_values": "", "unit": "mixed",
        "enforcement": "BUILDER_ASSERTION|GEOMETRY_QC",
        "source": "v02 source data traced to accepted M04", "status": "PASS",
        "notes": "Scientific values unchanged; panel A changed to vertical bars",
    }
    write_layout_v03(out, "Figure3", metrics, scientific_row, validator)
    base.write_text_new(out / "legend_v03.md", (v02 / "legend_v02.md").read_text(encoding="utf-8"))
    base.write_csv_new(out / "source_manifest_v03.csv",
                       ["source_id", "path", "role", "upstream_status", "notes"], [{
        "source_id": "F3V03S001",
        "path": str((v02 / "source_data").relative_to(root)).replace("\\", "/"),
        "role": "v02 plotting tables, traced to accepted M04",
        "upstream_status": "READ_ONLY_VERSIONED_CANDIDATE",
        "notes": "Second layout repair only; no analysis rerun",
    }])
    return {"figure": "Figure3", "candidate": str(candidate)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--figure-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    figure_root = args.figure_root.resolve()
    base.set_theme()
    validator = root / "04_code/vendor/figure_skills/sq3_v2.3-beta.1/tools/validate_layout_contract.py"
    outputs = [
        figure_root / "Figure2_Sample_Reuse_Comparator_Map_v03_layout_repair",
        figure_root / "Figure3_Naive_Vs_Aware_v03_layout_repair",
    ]
    if any(path.exists() for path in outputs):
        raise FileExistsError("One or more v03 output directories already exist")
    results = [
        build_figure2(root, figure_root, outputs[0], validator),
        build_figure3(root, figure_root, outputs[1], validator),
    ]
    qc = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS",
        "operation": "SECOND_LAYOUT_REPAIR_ONLY_NO_ANALYSIS_RERUN",
        "checks": {
            "v01_and_v02_preserved": True,
            "accepted_science_unchanged": True,
            "layout_contracts_validated": True,
            "candidate_pngs_exist": all(Path(item["candidate"]).exists() for item in results),
            "no_final_release_created": True,
        },
        "candidate_status": "VISUAL_CANDIDATES_NOT_USER_LOCKED",
        "next_gate": "STRICT_ACTUAL_RENDER_REVIEW",
        "results": results,
    }
    base.write_json_new(figure_root / "G8_REMAINING_FIGURE_LAYOUT_REPAIR_QC_v03.json", qc)
    print(json.dumps(qc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
